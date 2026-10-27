"""Limit temporary ray/triangle candidate arrays in Crosshair stage 4."""

import os


def intersect_rays(mesh, ray_origins, ray_directions, multiple_hits=False):
    import numpy as np

    batch_size = int(os.environ.get("AUTOMATA_RAY_BATCH_SIZE", "64"))
    if batch_size <= 0:
        raise ValueError("Ray batch size must be positive.")
    if len(ray_origins) != len(ray_directions):
        raise ValueError("Ray origins and directions must have equal lengths.")
    faces, rays = [], []
    intersector = mesh.ray
    print(f"  Ray casting in batches of {batch_size}", flush=True)
    for start in range(0, len(ray_origins), batch_size):
        stop = start + batch_size
        face_hits, ray_hits = intersector.intersects_id(
            ray_origins=ray_origins[start:stop],
            ray_directions=ray_directions[start:stop],
            multiple_hits=multiple_hits,
        )
        if len(ray_hits):
            faces.append(np.asarray(face_hits, dtype=np.int64))
            rays.append(np.asarray(ray_hits, dtype=np.int64) + start)
    if not faces:
        return np.empty(0, dtype=np.int64), np.empty(0, dtype=np.int64)
    return np.concatenate(faces), np.concatenate(rays)
