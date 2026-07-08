# fmax sweep

| design | opencell7 (MHz) | asap7 (MHz) | gap vs asap7 |
|--------|-----------------|-------------|--------------|
| picorv32 | 2002 | 2349 | -14.8% |

```json
[
  {
    "platform": "opencell7",
    "design": "picorv32",
    "fmax_mhz": 2002,
    "period_ps": 500.0,
    "converged": true,
    "iters_used": 2,
    "history": [
      {
        "iter": 0,
        "target_ps": 500.0,
        "achieved_ps": 500.0,
        "fmax_mhz": 2002
      },
      {
        "iter": 1,
        "target_ps": 500.0,
        "achieved_ps": 500.0,
        "fmax_mhz": 2002
      }
    ],
    "status": "OK",
    "error": "",
    "wall_s": 369.7,
    "run": 1
  },
  {
    "platform": "opencell7",
    "design": "picorv32",
    "fmax_mhz": 2002,
    "period_ps": 500.0,
    "converged": true,
    "iters_used": 2,
    "history": [
      {
        "iter": 0,
        "target_ps": 500.0,
        "achieved_ps": 500.0,
        "fmax_mhz": 2002
      },
      {
        "iter": 1,
        "target_ps": 500.0,
        "achieved_ps": 500.0,
        "fmax_mhz": 2002
      }
    ],
    "status": "OK",
    "error": "",
    "wall_s": 372.5,
    "run": 2
  },
  {
    "platform": "asap7",
    "design": "picorv32",
    "fmax_mhz": 2349,
    "period_ps": 425.6,
    "converged": true,
    "iters_used": 2,
    "history": [
      {
        "iter": 0,
        "target_ps": 458.1,
        "achieved_ps": 434.6,
        "fmax_mhz": 2301
      },
      {
        "iter": 1,
        "target_ps": 434.6,
        "achieved_ps": 425.6,
        "fmax_mhz": 2349
      }
    ],
    "status": "OK",
    "error": "",
    "wall_s": 385.0,
    "run": 1
  },
  {
    "platform": "asap7",
    "design": "picorv32",
    "fmax_mhz": 2349,
    "period_ps": 425.6,
    "converged": true,
    "iters_used": 2,
    "history": [
      {
        "iter": 0,
        "target_ps": 458.1,
        "achieved_ps": 434.6,
        "fmax_mhz": 2301
      },
      {
        "iter": 1,
        "target_ps": 434.6,
        "achieved_ps": 425.6,
        "fmax_mhz": 2349
      }
    ],
    "status": "OK",
    "error": "",
    "wall_s": 370.3,
    "run": 2
  }
]
```
