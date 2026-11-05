"""Rebuild constant-depth extrusions with circular holes and rounded outlines."""
import numpy as np


def circle(points, epsilon):
    origin = points.mean(axis=0)
    q = points-origin
    a = np.column_stack([2*q, np.ones(len(q))])
    answer, _, rank, _ = np.linalg.lstsq(a, np.sum(q*q, axis=1), rcond=None)
    if rank < 3:
        return None
    center = origin+answer[:2]
    radius = float(np.sqrt(max(0, answer[2]+np.dot(answer[:2], answer[:2]))))
    if radius <= epsilon or np.max(np.abs(np.linalg.norm(points-center, axis=1)-radius)) > epsilon:
        return None
    return center, radius


def loops_from_edges(edges):
    graph = {}
    for a, b in edges:
        graph.setdefault(int(a), set()).add(int(b))
        graph.setdefault(int(b), set()).add(int(a))
    if not graph or any(len(v) != 2 for v in graph.values()):
        return None
    remaining, loops = set(graph), []
    while remaining:
        start = min(remaining)
        path, previous, current = [], None, start
        while current not in path:
            path.append(current)
            next_id = sorted(graph[current]-{previous})[0]
            previous, current = current, next_id
        if current != start:
            return None
        remaining -= set(path)
        loops.append(path)
    return loops


def signed_area(points):
    return float(np.sum(points[:, 0]*np.roll(points[:, 1], -1)-points[:, 1]*np.roll(points[:, 0], -1))/2)


def contour_wire(points, origin, axis, u, v, epsilon):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire
    from OCP.GC import GC_MakeArcOfCircle
    from OCP.gp import gp_Pnt, gp_Dir, gp_Ax2, gp_Circ
    from OCP.TopoDS import TopoDS
    def point(q):
        return gp_Pnt(*(origin+q[0]*u+q[1]*v))
    fitted = circle(points, epsilon)
    if len(points) >= 12 and fitted is not None:
        center, radius = fitted
        theta = np.sort(np.arctan2(*(points-center)[:, ::-1].T))
        if np.diff(np.r_[theta, theta[0]+2*np.pi]).max() < np.pi/4:
            wire = BRepBuilderAPI_MakeWire(BRepBuilderAPI_MakeEdge(
                gp_Circ(gp_Ax2(point(center), gp_Dir(*axis), gp_Dir(*u)), radius)).Edge()).Wire()
            if signed_area(points) < 0:
                wire = TopoDS.Wire_s(wire.Reversed())
            theta = np.arange(192)*2*np.pi/192
            sample2d = center+radius*np.column_stack([np.cos(theta), np.sin(theta)])
            return wire, sample2d, [{'type': 'circle', 'center_uv': center.tolist(), 'radius': radius}]
    # Start after a long straight edge so a rounded corner rarely straddles the
    # seam. Fully circular loops are handled above.
    points = np.roll(points, -(np.argmax(np.linalg.norm(np.roll(points, -1, axis=0)-points, axis=1))+1), axis=0)
    points = np.vstack([points, points[0]])
    count, segments, index = len(points)-1, [], 0
    while index < count:
        best = None
        for end in range(index+4, min(count, index+128)+1):
            fit = circle(points[index:end+1], epsilon)
            if fit is None:
                break
            center, radius = fit
            angle = np.unwrap(np.arctan2((points[index:end+1]-center)[:, 1],
                                         (points[index:end+1]-center)[:, 0]))
            increments = np.diff(angle)
            if (not (np.all(increments > 0) or np.all(increments < 0)) or
                    np.max(np.abs(increments)) > np.pi/4 or abs(angle[-1]-angle[0]) >= 2*np.pi-.01):
                break
            if abs(angle[-1]-angle[0]) >= np.pi/12:
                best = (end, center, radius, float((angle[0]+angle[-1])/2))
        if best is None:
            segments.append(('line', index, index+1, None))
            index += 1
        else:
            end, center, radius, mid_angle = best
            segments.append(('arc', index, end, (center, radius, mid_angle)))
            index = end
    builder, samples, parameters = BRepBuilderAPI_MakeWire(), [], []
    for kind, start, end, fit in segments:
        a, b = points[start], points[end]
        if np.linalg.norm(b-a) <= epsilon:
            return None
        if kind == 'line':
            builder.Add(BRepBuilderAPI_MakeEdge(point(a), point(b)).Edge())
            t = np.linspace(0, 1, 9)
            samples.append(a+t[:, None]*(b-a))
            parameters.append({'type': 'line', 'start_uv': a.tolist(), 'end_uv': b.tolist()})
        else:
            center, radius, mid_angle = fit
            mid = center+radius*np.array([np.cos(mid_angle), np.sin(mid_angle)])
            arc = GC_MakeArcOfCircle(point(a), point(mid), point(b)).Value()
            builder.Add(BRepBuilderAPI_MakeEdge(arc).Edge())
            params = np.linspace(arc.FirstParameter(), arc.LastParameter(), 96)
            xyz = np.array([arc.Value(float(t)).Coord() for t in params])
            samples.append(np.column_stack([(xyz-origin)@u, (xyz-origin)@v]))
            parameters.append({'type': 'arc', 'fitted_radius': radius,
                               'start_uv': a.tolist(), 'end_uv': b.tolist(), 'center_uv': center.tolist()})
    if not builder.IsDone():
        return None
    return builder.Wire(), np.concatenate(samples), parameters


def extrusion_candidate(mesh, origin, axis, tolerance):
    from .surfaces import Candidate, frame
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeVertex
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
    from OCP.BRepClass import BRepClass_FaceClassifier
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.TopAbs import TopAbs_IN, TopAbs_ON, TopAbs_SHELL
    from OCP.gp import gp_Pnt, gp_Vec
    from .geometry import subshapes
    from shapely.geometry import Polygon
    u, v = frame(axis)
    q = mesh.vertices-origin
    heights = q@axis
    epsilon = max(mesh.scale*2e-6, tolerance*.005)
    low, high = heights.min(), heights.max()
    if high-low < epsilon*10 or np.any(np.minimum(heights-low, high-heights) > epsilon):
        return None  # Constant-depth extrusion only; don't flatten varying depth.
    low = float(heights[np.abs(heights-low) < epsilon].mean())
    high = float(heights[np.abs(heights-high) < epsilon].mean())
    top = np.abs(heights-high) <= epsilon
    cap_faces = mesh.faces[top[mesh.faces].all(axis=1)]
    if not len(cap_faces):
        return None
    edges = np.sort(cap_faces[:, [[0, 1], [1, 2], [2, 0]]].reshape(-1, 2), axis=1)
    unique, counts = np.unique(edges, axis=0, return_counts=True)
    loops = loops_from_edges(unique[counts == 1])
    if not loops or sum(map(len, loops)) > 1024:
        return None
    uv = np.column_stack([q@u, q@v])
    contours = [uv[loop].copy() for loop in loops]
    outer = int(np.argmax([abs(signed_area(p)) for p in contours]))
    contours[0], contours[outer] = contours[outer], contours[0]
    polygons = [Polygon(p) for p in contours]
    if not all(p.is_valid for p in polygons) or not all(polygons[0].contains(p) for p in polygons[1:]):
        return None
    origin = origin+low*axis
    height = high-low
    wires, side_samples, parameters = [], [], []
    for i, contour in enumerate(contours):
        if (signed_area(contour) > 0) != (i == 0):
            contour = contour[::-1]
        result = contour_wire(contour, origin, axis, u, v, epsilon)
        if result is None:
            return None
        wire, points2d, curves = result
        wires.append(wire)
        parameters.append({'role': 'outer' if i == 0 else 'hole', 'curves': curves})
        base = origin+points2d[:, 0, None]*u+points2d[:, 1, None]*v
        side_samples.append((base[:, None, :]+np.linspace(0, height, 7)[None, :, None]*axis).reshape(-1, 3))
    if not any(c['type'] in {'circle', 'arc'} for p in parameters for c in p['curves']):
        return None
    if sum(len(p['curves']) for p in parameters) > 80:
        return None
    face_builder = BRepBuilderAPI_MakeFace(wires[0])
    for wire in wires[1:]:
        face_builder.Add(wire)
    face = face_builder.Face()
    shape = BRepPrimAPI_MakePrism(face, gp_Vec(*(axis*height))).Shape()
    shells = list(subshapes(shape, TopAbs_SHELL))
    if len(shells) != 1:
        return None
    def distance(points):
        distances = []
        for p in points:
            query = BRepExtrema_DistShapeShape(BRepBuilderAPI_MakeVertex(gp_Pnt(*p)).Vertex(), shells[0])
            query.Perform()
            if not query.IsDone():
                raise ValueError('Cannot evaluate extrusion surface distance')
            distances.append(query.Value())
        return np.array(distances)
    # Cap probes inside the actual trimmed face, plus exact boundary/side probes.
    cap_points = mesh.vertices[cap_faces].mean(axis=1)
    indices = np.linspace(0, len(cap_points)-1, min(2048, len(cap_points)), dtype=int)
    cap_samples = []
    for p in cap_points[indices]:
        p = p-axis*np.dot(p-origin, axis)
        if BRepClass_FaceClassifier(face, gp_Pnt(*p), 1e-7).State() in (TopAbs_IN, TopAbs_ON):
            cap_samples.extend([p, p+axis*height])
    samples = np.vstack([*side_samples, np.asarray(cap_samples).reshape(-1, 3)])
    return Candidate(shape, distance, samples,
                     {'type': 'extrusion', 'origin': origin.tolist(), 'axis': axis.tolist(),
                      'u': u.tolist(), 'v': v.tolist(), 'height': height, 'contours': parameters,
                      'holes_preserved': len(wires)-1}, 2-2*(len(wires)-1))
