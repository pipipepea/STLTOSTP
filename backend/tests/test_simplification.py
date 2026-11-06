import numpy as np
import pytest
import trimesh
from app.geometry import convert, load_mesh
from app.simplification import simplify, feature_distance


def dense_box(level=4):
    mesh = trimesh.creation.box(extents=[10, 12, 15])
    for _ in range(level):
        mesh = mesh.subdivide()
    return mesh


def test_large_input_reduces_below_cad_limit_and_keeps_sharp_edges():
    mesh = dense_box(6)  # 49,152 triangles, greater than the user's 45,844.
    report = {}
    reduced = simplify(mesh, 25000, .05, report)
    assert len(mesh.faces) == 49152 and len(reduced.faces) <= 25000
    assert report['accepted'] and report['applied']
    assert reduced.is_watertight and reduced.euler_number == mesh.euler_number
    assert reduced.volume == pytest.approx(mesh.volume, rel=.01)
    assert all(v['passed'] for v in report['components'][0]['sharp_edges'].values())


def test_reduction_step_roundtrip_and_original_bytes_preserved(tmp_path, monkeypatch):
    from app import geometry
    monkeypatch.setattr(geometry, 'MAX_FACES', 1000)
    source = tmp_path/'source.stl'
    dense_box().export(source)
    original_bytes = source.read_bytes()
    report = convert(source, tmp_path, simplify_mesh=True, target_faces=800)
    assert report['success'], report
    assert report['before']['faces'] == 3072
    assert report['after']['faces'] == 3072
    assert report['conversion_mesh']['faces'] <= 800
    assert report['verification']['after_reimport']['faces'] == 6
    assert report['verification']['original_surface_deviation']['passed']
    assert source.read_bytes() == original_bytes
    assert (tmp_path/'simplified.stl').exists()
    assert (tmp_path/'repaired.stl').exists()


def test_disabled_reduction_does_not_silently_change_large_mesh(tmp_path, monkeypatch):
    from app import geometry
    monkeypatch.setattr(geometry, 'MAX_FACES', 1000)
    dense_box().export(tmp_path/'source.stl')
    report = convert(tmp_path/'source.stl', tmp_path)
    assert not report['success']
    assert 'Bật Giảm lưới' in report['error']
    assert report['before']['faces'] == 3072
    assert not (tmp_path/'result.step').exists()
    assert not (tmp_path/'simplified.stl').exists()


def test_too_tight_deviation_is_rejected_and_candidate_not_published(tmp_path):
    mesh = trimesh.creation.icosphere(subdivisions=3, radius=5)
    mesh.export(tmp_path/'source.stl')
    report = convert(tmp_path/'source.stl', tmp_path, simplify_mesh=True,
                     target_faces=1000, simplify_tolerance=1e-7)
    assert not report['success']
    assert not report['simplification']['accepted']
    assert 'rejection_reason' in report['simplification']
    assert not (tmp_path/'simplified.stl').exists()
    assert not (tmp_path/'result.step').exists()


def test_preserves_small_disconnected_component():
    mesh = dense_box(3)
    small = trimesh.creation.box(extents=[.2, .2, .2])
    small.apply_translation([20, 0, 0])
    report = {}
    reduced = simplify(mesh+small, 500, .05, report)
    parts = reduced.split(only_watertight=False, repair=False)
    assert len(parts) == 2
    assert min(abs(p.volume) for p in parts) == pytest.approx(.008, rel=.01)


def test_open_mesh_is_not_closed_by_reduction():
    mesh = dense_box(3)
    mesh.update_faces(np.arange(len(mesh.faces)-1))
    with pytest.raises(ValueError, match='lưới kín'):
        simplify(mesh, 100, .05, {})


def test_already_under_target_is_unchanged():
    mesh = trimesh.creation.box()
    report = {}
    result = simplify(mesh, 500, .05, report)
    assert result is mesh and report['accepted'] and not report['applied']


def test_input_face_limit_is_separate_from_cad_limit(tmp_path, monkeypatch):
    from app import geometry
    dense_box(2).export(tmp_path/'source.stl')
    monkeypatch.setattr(geometry, 'MAX_FACES', 10)
    assert len(load_mesh(tmp_path/'source.stl').faces) > 10
    monkeypatch.setattr(geometry, 'MAX_INPUT_FACES', 10)
    with pytest.raises(ValueError, match='giới hạn đọc STL'):
        load_mesh(tmp_path/'source.stl')


def test_sharp_feature_disappearance_is_rejected():
    segments = np.array([[[0., 0, 0], [1., 0, 0]]])
    assert not feature_distance(segments, np.empty((0, 2, 3)), .05)['passed']


def test_topology_changing_result_is_rejected(monkeypatch):
    from app import simplification
    mesh = dense_box(3)
    def broken(part, target, tolerance):
        return part+trimesh.creation.box()
    monkeypatch.setattr(simplification, 'decimate_part', broken)
    with pytest.raises(ValueError, match='topology'):
        simplify(mesh, 100, .05, {})


def test_reduction_then_curved_fit_is_also_compared_with_original(tmp_path):
    mesh = trimesh.creation.icosphere(subdivisions=4, radius=5)
    mesh.export(tmp_path/'source.stl')
    report = convert(tmp_path/'source.stl', tmp_path, simplify_mesh=True, target_faces=2000,
                     curve_mode='auto', simplify_tolerance=.05, fit_tolerance=.05)
    assert report['success'], report
    assert report['surface_types'] == {'sphere': 1}
    assert report['curve_reconstruction']['reference_mesh'] == 'simplified'
    check = report['verification']['original_surface_deviation']
    assert check['passed']
    assert check['reduction_and_fit_budget'] == pytest.approx(.1)
