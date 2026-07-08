# fmax sweep

| design | opencell7 (MHz) | asap7 (MHz) | gap vs asap7 |
|--------|-----------------|-------------|--------------|
| d8 | 7246 | 7687 | -5.7% |

```json
[
  {
    "platform": "opencell7",
    "design": "d8",
    "fmax_mhz": 7246,
    "period_ps": 140.0,
    "converged": true,
    "iters_used": 2,
    "history": [
      {
        "iter": 0,
        "target_ps": 150.0,
        "achieved_ps": 140.0,
        "fmax_mhz": 7130
      },
      {
        "iter": 1,
        "target_ps": 140.0,
        "achieved_ps": 140.0,
        "fmax_mhz": 7246
      }
    ],
    "status": "OK",
    "error": "",
    "wall_s": 87.9,
    "run": 1
  },
  {
    "platform": "asap7",
    "design": "d8",
    "fmax_mhz": 7687,
    "period_ps": 130.1,
    "converged": true,
    "iters_used": 2,
    "history": [
      {
        "iter": 0,
        "target_ps": 130.4,
        "achieved_ps": 130.1,
        "fmax_mhz": 7687
      },
      {
        "iter": 1,
        "target_ps": 130.1,
        "achieved_ps": 130.1,
        "fmax_mhz": 7687
      }
    ],
    "status": "OK",
    "error": "",
    "wall_s": 90.8,
    "run": 1
  }
]
```
