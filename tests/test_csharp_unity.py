"""
Tests for C# method-invocation call graph, [SerializeField] field references,
Unity .meta/.prefab/.unity/.asset GUID & UnityEvent wiring, method-level
pm_find / pm_impact routing, and Unity-aware pm_orphans filtering.
"""

from __future__ import annotations

from pathlib import Path

from project_mapper.analyzers import analyze_file, detect_language_for_path
from project_mapper.analyzers.csharp import analyze_csharp
from project_mapper.core.cleanup import prune_orphan_stubs, resolve_stubs
from project_mapper.core.ingestor import ProjectIngestor
from project_mapper.core.query import (
    build_entity_map,
    find_by_method,
    impact_query,
    orphan_query,
)
from project_mapper.db.file_manifest import FileManifest
from project_mapper.db.pm_store import PMEntityStore, PMNameIndex
from project_mapper.mcp.tools.base import MCPContext
from project_mapper.mcp.tools.find import handle_pm_find
from project_mapper.mcp.tools.impact import handle_pm_impact


def test_csharp_method_invocations_and_serialize_fields():
    code = """\
using System.Collections.Generic;
using UnityEngine;

public class CombatController : MonoBehaviour
{
    [SerializeField] private PlayerScript _player;
    [SerializeField] private List<WeaponData> _weapons;
    private AudioManager _audio;

    private void Awake()
    {
        _audio = GetComponent<AudioManager>();
    }

    public void TakeHit(int dmg)
    {
        GameHandler.instance.Death();
        Connector.Instance.Haptics.Pulse();
        Get_PlayerScript().TriggerScreenShake(0.5f);
        _player.On_Damage(dmg);
        _audio.PlayHitSound();
    }
}
"""
    analysis = analyze_csharp(Path("CombatController.cs"), code)
    assert len(analysis.classes) == 1
    cls = analysis.classes[0]
    assert cls.name == "CombatController"

    # Singleton, factory, generic, and field receiver targets should be in cls.calls
    callee_names = {callee for callee, _via in cls.calls}
    assert "GameHandler" in callee_names
    assert "Connector" in callee_names
    assert "PlayerScript" in callee_names
    assert "AudioManager" in callee_names

    # [SerializeField] and typed instance fields should be captured
    field_map = {(fname, ftype): is_ser for fname, ftype, is_ser in cls.field_refs}
    assert field_map.get(("_player", "PlayerScript")) is True
    assert field_map.get(("_weapons", "WeaponData")) is True
    assert field_map.get(("_audio", "AudioManager")) is False

    # Method-level call triples (receiver_hint, called_method, via_method)
    mc_set = set(cls.method_calls)
    assert ("GameHandler", "Death", "TakeHit") in mc_set
    assert ("Haptics", "Pulse", "TakeHit") in mc_set
    assert ("PlayerScript", "TriggerScreenShake", "TakeHit") in mc_set
    assert ("PlayerScript", "On_Damage", "TakeHit") in mc_set
    assert ("AudioManager", "PlayHitSound", "TakeHit") in mc_set

    # Method line numbers should be populated
    method_by_name = {m.name: m for m in cls.methods}
    assert method_by_name["TakeHit"].line_start == 15
    assert method_by_name["TakeHit"].line_end == 22


def test_unity_project_scan_impact_find_and_orphans(tmp_path: Path):
    assets = tmp_path / "Assets"
    scripts = assets / "Scripts"
    prefabs = assets / "Prefabs"
    scenes = assets / "Scenes"
    scripts.mkdir(parents=True)
    prefabs.mkdir(parents=True)
    scenes.mkdir(parents=True)

    # 1. PlayerScript.cs + .meta
    player_guid = "a1b2c3d4e5f60718293a4b5c6d7e8f90"
    (scripts / "PlayerScript.cs").write_text(
        """\
using UnityEngine;

public class PlayerScript : MonoBehaviour
{
    public void TriggerScreenShake(float intensity)
    {
    }

    public void On_Damage(int amount)
    {
        TriggerScreenShake(0.2f);
    }

    public void GoingUnderwater()
    {
    }
}
""",
        encoding="utf-8",
    )
    (scripts / "PlayerScript.cs.meta").write_text(
        f"fileFormatVersion: 2\nguid: {player_guid}\nMonoImporter:\n  externalObjects: {{}}\n",
        encoding="utf-8",
    )

    # 2. GameHandler.cs + .meta
    gh_guid = "b2c3d4e5f60718293a4b5c6d7e8f90a1"
    (scripts / "GameHandler.cs").write_text(
        """\
using UnityEngine;

public class GameHandler : MonoBehaviour
{
    public static GameHandler instance;

    public void Death()
    {
    }

    public void OnClickRestart()
    {
    }
}
""",
        encoding="utf-8",
    )
    (scripts / "GameHandler.cs.meta").write_text(
        f"fileFormatVersion: 2\nguid: {gh_guid}\n",
        encoding="utf-8",
    )

    # 3. CombatController.cs (calls TriggerScreenShake & Death, holds [SerializeField] PlayerScript)
    (scripts / "CombatController.cs").write_text(
        """\
using UnityEngine;

public class CombatController : MonoBehaviour
{
    [SerializeField] private PlayerScript _player;

    public void ApplyDamage(int dmg)
    {
        Get_PlayerScript().TriggerScreenShake(0.5f);
        GameHandler.instance.Death();
    }
}
""",
        encoding="utf-8",
    )

    # 4. ExplosionHazard.cs (also calls TriggerScreenShake)
    (scripts / "ExplosionHazard.cs").write_text(
        """\
using UnityEngine;

public class ExplosionHazard : MonoBehaviour
{
    public void Detonate()
    {
        Get_PlayerScript().TriggerScreenShake(1.0f);
    }
}
""",
        encoding="utf-8",
    )

    # 5. Substring class name to test that pm_find TriggerScreenShake still resolves the method first
    (scripts / "TriggerScreenShakeConfig.cs").write_text(
        """\
using UnityEngine;

public class TriggerScreenShakeConfig : ScriptableObject
{
    public float defaultDuration = 0.25f;
}
""",
        encoding="utf-8",
    )

    # 6. Unity Editor script (implicit Unity entry point — should NOT be flagged as orphan)
    (scripts / "PlayerScriptEditor.cs").write_text(
        """\
using UnityEditor;

[CustomEditor(typeof(PlayerScript))]
public class PlayerScriptEditor : Editor
{
}
""",
        encoding="utf-8",
    )

    # 7. Unused class (genuinely dead code — SHOULD be flagged as orphan)
    (scripts / "UnusedLegacyHelper.cs").write_text(
        """\
public class UnusedLegacyHelper
{
    public void OldMethod() {}
}
""",
        encoding="utf-8",
    )

    # 8. Player.prefab attaching PlayerScript via GUID (deliberately ingested BEFORE scripts to test deferred GUID resolution)
    (prefabs / "Player.prefab").write_text(
        f"""\
%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!114 &11400000
MonoBehaviour:
  m_ObjectHideFlags: 0
  m_Script: {{fileID: 11500000, guid: {player_guid}, type: 3}}
""",
        encoding="utf-8",
    )

    # 9. MainScene.unity attaching GameHandler via GUID and wiring OnClickRestart via UnityEvent
    (scenes / "MainScene.unity").write_text(
        f"""\
%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!114 &11400001
MonoBehaviour:
  m_Script: {{fileID: 11500000, guid: {gh_guid}, type: 3}}
  m_OnClick:
    m_PersistentCalls:
      m_Calls:
      - m_Target: {{fileID: 11400001}}
        m_TargetAssemblyTypeName: GameHandler, Assembly-CSharp
        m_MethodName: OnClickRestart
""",
        encoding="utf-8",
    )

    db_dir = tmp_path / ".pm"
    db_dir.mkdir(parents=True, exist_ok=True)
    index = PMNameIndex(index_path=db_dir / "name_index.json")
    writer = PMEntityStore(db_dir, index)
    manifest = FileManifest(db_dir)
    ingestor = ProjectIngestor(db_root=db_dir, writer=writer, index=index, file_manifest=manifest)

    # Ingest prefabs/scenes first, then scripts, to exercise both immediate and deferred resolution
    files_to_ingest = [
        prefabs / "Player.prefab",
        scenes / "MainScene.unity",
        scripts / "CombatController.cs",
        scripts / "ExplosionHazard.cs",
        scripts / "TriggerScreenShakeConfig.cs",
        scripts / "PlayerScriptEditor.cs",
        scripts / "UnusedLegacyHelper.cs",
        scripts / "PlayerScript.cs",
        scripts / "GameHandler.cs",
    ]
    for fp in files_to_ingest:
        rel = str(fp.relative_to(tmp_path)).replace("\\", "/")
        content = fp.read_text(encoding="utf-8")
        lang = detect_language_for_path(str(fp))
        analysis = analyze_file(rel, content, lang)
        ingestor.ingest(analysis, tmp_path)

    resolve_stubs(writer, index)
    prune_orphan_stubs(writer)

    ctx = MCPContext(
        db_root=db_dir,
        db_name="test_unity",
        writer=writer,
        index=index,
        file_manifest=manifest,
        project_root=str(tmp_path),
    )

    entity_map = build_entity_map(writer)

    # --- Test 1: pm_impact TriggerScreenShake finds all call sites ---
    impact_res = impact_query("TriggerScreenShake", entity_map, index, max_depth=2)
    assert not impact_res["not_found"]
    assert impact_res["subject"]["name"] == "PlayerScript.TriggerScreenShake"
    assert impact_res["subject"]["line"] == 5

    hop1_names = {item["name"] for item in impact_res["affected"] if item["hop"] == 1}
    assert "CombatController" in hop1_names
    assert "ExplosionHazard" in hop1_names

    # Check that calling method line number is resolved on CombatController (ApplyDamage is line 7)
    combat_hit = next(item for item in impact_res["affected"] if item["name"] == "CombatController")
    assert combat_hit["line"] == 7
    assert "ApplyDamage" in combat_hit["via"]

    # Check formatted MCP output for pm_impact
    impact_text = handle_pm_impact({"entity": "TriggerScreenShake"}, ctx)
    assert "PlayerScript.TriggerScreenShake" in impact_text
    assert "CombatController" in impact_text
    assert "ExplosionHazard" in impact_text

    # --- Test 2: pm_find TriggerScreenShake resolves method & callers (even with substring class) ---
    find_text = handle_pm_find({"name": "TriggerScreenShake"}, ctx)
    assert "Method: PlayerScript.TriggerScreenShake" in find_text
    assert "CombatController" in find_text
    assert "ExplosionHazard" in find_text

    # Also test find_by_method directly
    m_res = find_by_method("TriggerScreenShake", entity_map, index)
    assert not m_res["not_found"]
    assert m_res["matches"][0]["name"] == "PlayerScript"
    assert m_res["matches"][0]["line_start"] == 5

    # --- Test 3: UnityEvent wiring on MainScene -> GameHandler.OnClickRestart ---
    restart_impact = impact_query("GameHandler.OnClickRestart", entity_map, index, max_depth=1)
    assert not restart_impact["not_found"]
    restart_callers = {item["name"] for item in restart_impact["affected"]}
    assert "Assets/Scenes/MainScene.unity" in restart_callers

    # --- Test 4: [SerializeField] field reference edges ---
    combat_entity = entity_map[index.get("CombatController")]
    assert "_player: PlayerScript" in combat_entity["sections"]["properties"].get("serialized_fields", "")

    # --- Test 5: pm_orphans does NOT false-positive on prefab/scene MonoBehaviours or Editor scripts ---
    orphans_res = orphan_query(entity_map)
    orphan_names = {o["name"] for o in orphans_res["orphans"]}
    assert "PlayerScript" not in orphan_names
    assert "GameHandler" not in orphan_names
    assert "PlayerScriptEditor" not in orphan_names
    # Genuinely unused helper class is still detected
    assert "UnusedLegacyHelper" in orphan_names
