"""Small deterministic mesh checks shared with the Blender worker.
These are topology checks, never a substitute for slicing or physical print QA.
"""
from collections import Counter
import math

def inspect_topology(vertices, faces):
    finite=bool(vertices) and all(len(v)==3 and all(math.isfinite(x) for x in v) for v in vertices)
    edges=Counter()
    degenerate=0
    invalid_indices=0
    for face in faces:
        if len(face)<3 or len(set(face))!=len(face): degenerate+=1
        if any(not isinstance(i,int) or i<0 or i>=len(vertices) for i in face):
            invalid_indices+=1
            continue
        for a,b in zip(face,face[1:]+face[:1]): edges[tuple(sorted((a,b)))]+=1
    boundary=sum(count==1 for count in edges.values())
    nonmanifold=sum(count!=2 for count in edges.values())
    return {'finite':finite,'boundary_edges':boundary,'nonmanifold_edges':nonmanifold,'degenerate_faces':degenerate,'invalid_index_faces':invalid_indices,'passed':finite and bool(faces) and not (nonmanifold or degenerate or invalid_indices)}
