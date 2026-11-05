"""Analytic reconstruction of complete rotational components, with measured gates.

This is deterministic geometric fitting, not an AI model or arbitrary patch sewing.
Distances are in source STL units. Sampled maxima are not Hausdorff bounds.
"""
from dataclasses import dataclass
from collections import Counter
from typing import Callable
import numpy as np
import trimesh


@dataclass
class Candidate:
    shape: object
    distance: Callable
    samples: np.ndarray
    parameters: dict
    euler: int


def summary(distances, points):
    worst = int(np.argmax(distances))
    return {'max': float(distances[worst]), 'rms': float(np.sqrt(np.mean(distances**2))),
            'p95': float(np.percentile(distances, 95)), 'samples': len(distances),
            'worst_point': points[worst].tolist()}


def mesh_probes(mesh):
    """Cover every triangle, vertex and edge; no random omission of small faces."""
    return np.concatenate([mesh.vertices, mesh.triangles_center,
                           mesh.vertices[mesh.edges_unique].mean(axis=1)])


def frame(axis):
    seed = np.eye(3)[np.argmin(np.abs(axis))]
    u = np.cross(axis, seed)
    u /= np.linalg.norm(u)
    return u, np.cross(axis, u)


def revolve_points(origin, axis, profile, angles=128):
    u, v = frame(axis)
    theta = np.arange(angles) * (2*np.pi/angles)
    directions = np.cos(theta)[:, None]*u + np.sin(theta)[:, None]*v
    # profile columns are axial height, radius.
    return (origin + profile[:, 0, None, None]*axis +
            profile[:, 1, None, None]*directions).reshape(-1, 3)


def projected(points, origin, axis):
    q = points-origin
    z = q @ axis
    r = np.linalg.norm(q-z[:, None]*axis, axis=1)
    return np.column_stack([z, r])


def profile_distance(points, origin, axis, profile):
    q = projected(points, origin, axis)
    result = np.full(len(q), np.inf)
    for a, b in zip(profile, np.roll(profile, -1, axis=0)):
        # An edge on the revolution axis is interior, not a solid surface.
        if max(a[1], b[1]) <= 1e-12:
            continue
        d = b-a
        t = np.clip((q-a) @ d / np.dot(d, d), 0, 1)
        result = np.minimum(result, np.linalg.norm(q-a-t[:, None]*d, axis=1))
    return result


def sphere_candidate(mesh, tolerance):
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeSphere
    from OCP.gp import gp_Pnt
    p = mesh.vertices
    origin = p.mean(axis=0)
    q = p-origin
    matrix = np.column_stack([2*q, np.ones(len(q))])
    answer, _, rank, _ = np.linalg.lstsq(matrix, np.sum(q*q, axis=1), rcond=None)
    if rank < 4:
        return None
    center = origin+answer[:3]
    radius = float(np.sqrt(max(0, answer[3]+np.dot(answer[:3], answer[:3]))))
    if radius <= 0 or np.max(np.abs(np.linalg.norm(p-center, axis=1)-radius)) > tolerance*.2:
        return None
    # Fibonacci coverage plus poles; reconstruction is a single exact sphere.
    i = np.arange(4096)
    z = 1-2*(i+.5)/len(i)
    theta = i*np.pi*(3-np.sqrt(5))
    r = np.sqrt(1-z*z)
    directions = np.column_stack([r*np.cos(theta), r*np.sin(theta), z])
    samples = center+radius*np.vstack([directions, np.eye(3), -np.eye(3)])
    return Candidate(BRepPrimAPI_MakeSphere(gp_Pnt(*center), radius).Shape(),
                     lambda points: np.abs(np.linalg.norm(points-center, axis=1)-radius), samples,
                     {'type': 'sphere', 'center': center.tolist(), 'radius': radius}, 2)


def axes(mesh):
    q = mesh.vertices-mesh.vertices.mean(axis=0)
    _, vectors = np.linalg.eigh(q.T @ q)
    normals = mesh.face_normals
    _, normal_vectors = np.linalg.eigh((normals*mesh.area_faces[:, None]).T @ normals)
    output = []
    for axis in np.concatenate([vectors.T, normal_vectors.T]):
        if not any(abs(axis @ old) > .999999 for old in output):
            output.append(axis)
    return output


def torus_candidate(mesh, origin, axis, tolerance):
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeTorus
    from OCP.gp import gp_Pnt, gp_Dir, gp_Ax2
    q = projected(mesh.vertices, origin, axis)
    # Circle in the meridian plane: (z-zc)^2+(r-R)^2=minor^2.
    answer, _, rank, _ = np.linalg.lstsq(np.column_stack([2*q, np.ones(len(q))]),
                                        np.sum(q*q, axis=1), rcond=None)
    if rank < 3:
        return None
    zc, major, c = answer
    minor = float(np.sqrt(max(0, c+zc*zc+major*major)))
    if minor <= 0 or major <= minor*1.05:
        return None  # No spindle/self-intersecting or horn tori.
    center = origin+axis*zc
    def distance(points):
        pr = projected(points, center, axis)
        return np.abs(np.sqrt(pr[:, 0]**2+(pr[:, 1]-major)**2)-minor)
    if distance(mesh.vertices).max() > tolerance*.2:
        return None
    theta = np.arange(48)*2*np.pi/48
    profile = np.column_stack([minor*np.sin(theta), major+minor*np.cos(theta)])
    samples = revolve_points(center, axis, profile, 96)
    shape = BRepPrimAPI_MakeTorus(gp_Ax2(gp_Pnt(*center), gp_Dir(*axis)), float(major), minor).Shape()
    return Candidate(shape, distance, samples, {'type': 'torus', 'center': center.tolist(),
                     'axis': axis.tolist(), 'major_radius': float(major), 'minor_radius': minor}, 0)


def cluster_profile(points, epsilon):
    # Streaming bounded spatial bins avoid quadratic query_pairs for a large ring.
    bins, centers, counts, inverse = {}, [], [], []
    for point in points:
        cell = tuple(np.floor(point/epsilon).astype(int))
        found = None
        for dz in (-1, 0, 1):
            for dr in (-1, 0, 1):
                for index in bins.get((cell[0]+dz, cell[1]+dr), ()):
                    if np.linalg.norm(point-centers[index]) <= epsilon:
                        found = index
                        break
                if found is not None:
                    break
            if found is not None:
                break
        if found is None:
            found = len(centers)
            if found >= 256:
                return None, None
            centers.append(point.copy())
            counts.append(0)
            bins.setdefault(cell, []).append(found)
        counts[found] += 1
        inverse.append(found)
    inverse = np.asarray(inverse)
    means = np.array([points[inverse == i].mean(axis=0) for i in range(len(centers))])
    return means, inverse


def rotational_candidate(mesh, origin, axis, tolerance):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon, BRepBuilderAPI_MakeFace
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeRevol
    from OCP.gp import gp_Pnt, gp_Dir, gp_Ax1
    q = projected(mesh.vertices, origin, axis)
    epsilon = max(mesh.scale*2e-6, tolerance*.005)
    nodes, inverse = cluster_profile(q, epsilon)
    if nodes is None or len(nodes) < 3:
        return None
    u, v = frame(axis)
    centered = mesh.vertices-origin
    for index, node in enumerate(nodes):
        if node[1] < epsilon:
            nodes[index, 1] = 0
            continue
        ring = centered[inverse == index]
        theta = np.unique(np.round(np.arctan2(ring@v, ring@u), 6))
        gaps = np.diff(np.r_[theta, theta[0]+2*np.pi])
        if len(theta) < 12 or gaps.max() > np.pi/4:
            return None  # Requires complete circular rings, not partial patches.
    edges = np.unique(np.sort(inverse[mesh.edges_unique], axis=1), axis=0)
    edges = edges[edges[:, 0] != edges[:, 1]]
    graph = {i: set() for i in range(len(nodes))}
    for a, b in edges:
        graph[int(a)].add(int(b))
        graph[int(b)].add(int(a))
    ends = [i for i, adjacent in graph.items() if len(adjacent) == 1]
    if len(ends) == 2 and np.max(nodes[ends, 1]) == 0:
        a, b = ends
        graph[a].add(b)
        graph[b].add(a)
    if any(len(adjacent) != 2 for adjacent in graph.values()):
        return None
    path, previous, current = [], None, 0
    for _ in range(len(nodes)):
        path.append(current)
        following = sorted(graph[current]-{previous})[0]
        previous, current = current, following
        if current == 0:
            break
    if current != 0 or len(path) != len(nodes):
        return None
    profile = nodes[path]
    # Float32 STL quantization introduces tiny axial/radial differences between
    # a cap center and its ring. Snap only below the ring-clustering resolution
    # so OCCT creates exact planes/cylinders rather than almost-planar sweeps.
    for coordinate in (0, 1):
        order = np.argsort(profile[:, coordinate])
        groups = []
        for index in order:
            if not groups or profile[index, coordinate]-profile[groups[-1][0], coordinate] > epsilon:
                groups.append([index])
            else:
                groups[-1].append(index)
        for group in groups:
            value = float(profile[group, coordinate].mean())
            if coordinate == 1 and value < epsilon:
                value = 0.0
            profile[group, coordinate] = value
    # Remove only collinear meridian nodes; keep every shoulder/chamfer corner.
    changed = True
    while changed and len(profile) > 3:
        changed = False
        for i in range(len(profile)):
            a, p, b = profile[i-1], profile[i], profile[(i+1) % len(profile)]
            d = b-a
            t = np.dot(p-a, d)/max(np.dot(d, d), 1e-30)
            if 0 < t < 1 and np.linalg.norm(p-a-t*d) < epsilon:
                profile = np.delete(profile, i, axis=0)
                changed = True
                break
    if len(profile) > 64:
        return None
    # Reject self-crossing meridian polygons explicitly before OCCT sweep.
    from shapely.geometry import Polygon
    polygon2d = Polygon(profile)
    if not polygon2d.is_valid or polygon2d.area <= epsilon**2:
        return None
    signed = np.sum(profile[:, 0]*np.roll(profile[:, 1], -1)-
                    profile[:, 1]*np.roll(profile[:, 0], -1))
    if signed < 0:
        profile = profile[::-1]
    polygon = BRepBuilderAPI_MakePolygon()
    for z, radius in profile:
        polygon.Add(gp_Pnt(*(origin+z*axis+radius*u)))
    polygon.Close()
    face = BRepBuilderAPI_MakeFace(polygon.Wire()).Face()
    shape = BRepPrimAPI_MakeRevol(face, gp_Ax1(gp_Pnt(*origin), gp_Dir(*axis))).Shape()
    samples, patches = [], []
    for a, b in zip(profile, np.roll(profile, -1, axis=0)):
        if max(a[1], b[1]) == 0:
            continue
        t = np.linspace(0, 1, 9)
        samples.append(revolve_points(origin, axis, a+t[:, None]*(b-a)))
        dz, dr = b-a
        kind = 'plane' if abs(dz) <= epsilon else 'cylinder' if abs(dr) <= epsilon else 'cone'
        patches.append({'type': kind, 'start_zr': a.tolist(), 'end_zr': b.tolist()})
    if not any(p['type'] != 'plane' for p in patches):
        return None
    parameters = {'type': 'revolution', 'origin': origin.tolist(), 'axis': axis.tolist(),
                  'profile_zr': profile.tolist(), 'patches': patches,
                  'sharp_profile_corners_preserved': True}
    return Candidate(shape, lambda points: profile_distance(points, origin, axis, profile),
                     np.concatenate(samples), parameters, 2 if np.min(profile[:, 1]) == 0 else 0)


def validate_candidate(mesh, candidate, tolerance, max_volume_change):
    from .geometry import shape_metrics
    metrics = shape_metrics(candidate.shape)
    if metrics['volume'] < 0:
        candidate.shape.Reverse()
        metrics = shape_metrics(candidate.shape)
    info = {'parameters': candidate.parameters, 'accepted': False}
    info['cad_bounds'] = metrics['bounds']
    info['cad_faces'] = metrics['faces']
    if not metrics['valid'] or metrics['solids'] != 1 or metrics['volume'] <= 0:
        return {**info, 'reason': 'CAD candidate is not a valid positive-volume solid'}
    if mesh.euler_number != candidate.euler:
        return {**info, 'reason': 'Candidate would change component topology (Euler characteristic)'}
    probes = mesh_probes(mesh)
    forward = candidate.distance(probes)
    info['mesh_to_cad'] = summary(forward, probes)
    volume_change = abs(metrics['volume']-abs(mesh.volume))/max(abs(mesh.volume), 1e-30)
    info['relative_volume_change'] = float(volume_change)
    info['bounds_max_change'] = float(np.max(np.abs(np.array(metrics['bounds'])-mesh.bounds)))
    if forward.max() > tolerance:
        return {**info, 'reason': 'Mesh-to-CAD deviation exceeds tolerance'}
    if volume_change > max_volume_change:
        return {**info, 'reason': 'Volume change exceeds configured limit'}
    if info['bounds_max_change'] > tolerance:
        return {**info, 'reason': 'Bounding-box change exceeds tolerance'}
    # Exact point-to-triangle distances using rtree broad phase, in bounded chunks.
    distances = []
    for offset in range(0, len(candidate.samples), 256):
        _, values, _ = trimesh.proximity.closest_point(mesh, candidate.samples[offset:offset+256])
        distances.append(values)
    reverse = np.concatenate(distances)
    info['cad_to_mesh'] = summary(reverse, candidate.samples)
    info['measurement'] = 'deterministic_surface_samples_not_certified_Hausdorff'
    if reverse.max() > tolerance:
        return {**info, 'reason': 'CAD-to-mesh deviation exceeds tolerance; preserving original facets'}
    return {**info, 'accepted': True, 'reason': 'Both sampled deviation directions and volume/topology gates passed'}


def reconstruct(mesh, tolerance, max_volume_change):
    """Return accepted shape or None, plus auditable attempts; no silent fitting."""
    attempts = []
    if tolerance > mesh.scale*.01:
        return None, {'accepted': False, 'attempts': [],
                      'reason': 'Fit tolerance exceeds 1% of component diagonal; reduce tolerance'}
    origin = mesh.vertices.mean(axis=0)
    from .extrusion import extrusion_candidate
    factories = [lambda: sphere_candidate(mesh, tolerance)]
    for axis in axes(mesh):
        factories.extend([lambda a=axis: torus_candidate(mesh, origin, a, tolerance),
                          lambda a=axis: rotational_candidate(mesh, origin, a, tolerance),
                          lambda a=axis: extrusion_candidate(mesh, origin, a, tolerance)])
    for factory in factories:
        try:
            candidate = factory()
            if candidate is None:
                continue
            info = validate_candidate(mesh, candidate, tolerance, max_volume_change)
            attempts.append(info)
            if info['accepted']:
                return candidate.shape, {**info, 'attempts': attempts[:-1]}
        except Exception as exc:
            # A fitting failure must not prevent the safe faceted path.
            attempts.append({'accepted': False, 'reason': f'Candidate construction failed: {type(exc).__name__}: {exc}'})
    return None, {'accepted': False, 'attempts': attempts,
                  'reason': 'No supported complete analytic component passed all gates'}


def surface_types(shape):
    from .geometry import subshapes
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.TopoDS import TopoDS
    from OCP.TopAbs import TopAbs_FACE
    counts = Counter()
    for face in subshapes(shape, TopAbs_FACE):
        name = BRepAdaptor_Surface(TopoDS.Face_s(face)).GetType().name.removeprefix('GeomAbs_').lower()
        counts[name] += 1
    return dict(counts)


def verify_step_distances(mesh, shape, components, tolerance):
    """Check points against actual re-imported STEP shells, not fitted equations."""
    from .geometry import subshapes, shape_metrics
    from OCP.TopAbs import TopAbs_SOLID, TopAbs_SHELL
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.gp import gp_Pnt
    parts = list(mesh.split(only_watertight=False, repair=False))
    solids = list(subshapes(shape, TopAbs_SOLID))
    boxes = np.array([shape_metrics(s)['bounds'] for s in solids])
    results = []
    for detail in components:
        if not detail['accepted']:
            continue
        expected = np.asarray(detail['cad_bounds'])
        index = int(np.argmin(np.max(np.abs(boxes-expected), axis=(1, 2))))
        shells = list(subshapes(solids[index], TopAbs_SHELL))
        if len(shells) != 1:
            raise ValueError('STEP sau nhập lại có số shell không khớp với thành phần phục dựng.')
        probes = mesh_probes(parts[detail['component']])
        indices = np.linspace(0, len(probes)-1, min(256, len(probes)), dtype=int)
        probes = np.vstack([probes[indices], detail['mesh_to_cad']['worst_point']])
        distances = []
        for point in probes:
            # A solid would report zero for interior points; use its shell to
            # measure distance to the boundary rather than occupied volume.
            query = BRepExtrema_DistShapeShape(BRepBuilderAPI_MakeVertex(gp_Pnt(*point)).Vertex(), shells[0])
            query.Perform()
            if not query.IsDone():
                raise ValueError('Không đo được khoảng cách tới bề mặt STEP sau nhập lại.')
            distances.append(query.Value())
        result = summary(np.asarray(distances), probes)
        result['component'] = detail['component']
        results.append(result)
        if result['max'] > tolerance+max(1e-7, mesh.scale*1e-8):
            raise ValueError('Sai lệch đến bề mặt STEP sau nhập lại vượt dung sai khớp.')
    return results
