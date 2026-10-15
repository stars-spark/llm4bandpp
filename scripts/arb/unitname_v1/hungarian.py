import numpy as np


def assign_min(C):
    """Solve the square min-cost assignment with the Hungarian algorithm in pure numpy (O(n^3)); return (rows, columns)."""
    C = np.asarray(C, float); n = C.shape[0]; INF = float("inf")
    u = np.zeros(n + 1); v = np.zeros(n + 1); p = np.zeros(n + 1, int); way = np.zeros(n + 1, int)
    for i in range(1, n + 1):
        p[0] = i; j0 = 0; minv = np.full(n + 1, INF); used = np.zeros(n + 1, bool)
        while True:
            used[j0] = True; i0 = p[j0]; delta = INF; j1 = 0
            for j in range(1, n + 1):
                if not used[j]:
                    cur = C[i0 - 1, j - 1] - u[i0] - v[j]
                    if cur < minv[j]: minv[j] = cur; way[j] = j0
                    if minv[j] < delta: delta = minv[j]; j1 = j
            for j in range(n + 1):
                if used[j]: u[p[j]] += delta; v[j] -= delta
                else: minv[j] -= delta
            j0 = j1
            if p[j0] == 0: break
        while True:
            j1 = way[j0]; p[j0] = p[j1]; j0 = j1
            if j0 == 0: break
    col_of_row = np.zeros(n, int)
    for j in range(1, n + 1): col_of_row[p[j] - 1] = j - 1
    return np.arange(n), col_of_row
