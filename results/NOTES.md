# Qué corrida es cada fichero — cuáles son válidos

Se conservan también las corridas superadas/inválidas a propósito, como evidencia de los errores
documentados en `../POSTMORTEM.md`. Esta tabla dice cuál usar para qué.

| Fichero | Tools | Dataset | Estado | Qué mide / por qué se conserva |
|---|---|---|---|---|
| `gemma4_31b_agent.json` | 5 | 15 tareas | Histórico | Corrida del 01/08 en **otra máquina**. Solo referencia — no comparar latencias con el resto (ver POSTMORTEM E9) |
| `gemma4_31b_agent_samegpu.json` | 5 | 15 tareas | **Válido** | `agent.py` hardcodeado, misma GPU que el resto → base de comparación real |
| `gemma4_31b_mcp_agent.json` | 5 | 15 tareas | **Válido** | `mcp_agent.py` vía MCP → resultado "MCP no cambia decisiones, +2.9% overhead" |
| `curve_core.json` / `curve_medium.json` / `curve_full_a.json` / `curve_full_b.json` | 5/12/19 | v1 (`agent_tasks_extended.json`) | **Inválido para % global** | Dataset v1 tenía 36/50 tareas inejecutables con catálogo de 5 tools (POSTMORTEM E5). Solo válida la intersección de 14 tareas resolubles en los tres. `full_a` vs `full_b` sí sirve tal cual → demuestra que `temperature 0` no es determinista en vLLM (3/50 tareas varían) |
| `v2_core.json` / `v2_medium.json` / `v2_full.json` | 5/12/20 | **v2** (`agent_tasks_v2.json`) | **Válido — curva definitiva** | Con reset de estado por tarea y catálogo corregido. `v2_full.json`: 49/50 |
| `v2_full_annotated.json` | 20 | v2 | **INVÁLIDO** | Bug POSTMORTEM E16: el puente MCP→OpenAI descartaba las `annotations` (`destructiveHint`, etc.), así que el prompt era idéntico al de `v2_full.json`. Se conserva solo como evidencia del bug |
| `v2_full_annotated2.json` | 20 | v2 | **Válido** | Igual que el anterior pero con el bug corregido — las annotations sí llegan al prompt. Resultado real: +26% tokens, cero seguridad ganada (POSTMORTEM H2) |

**Regla rápida:** para citar un número, usar `v2_full.json`, `v2_full_annotated2.json`,
`gemma4_31b_agent_samegpu.json` y `gemma4_31b_mcp_agent.json`. Todo lo demás es o bien histórico
(no comparable) o bien evidencia de un error ya corregido.

## Diagnóstico de causa raíz de T08 (12/08/2026) — gpt-4o, local

Ver `T08_ROOT_CAUSE_FIX.md` / `INFORME_CAUSA_RAIZ_T08.md` para la narrativa completa. **No
comparable con las corridas de arriba**: modelo distinto (gpt-4o vía API real, no self-hosted),
máquina local con Postgres desechable en Docker (no la instancia Vast.ai), y solo 3/12 tareas del
dataset completo, no las 50.

| Fichero | Qué mide | Estado |
|---|---|---|
| `gpt4o_t08_fix4_rep1/2/3.json` | T08 aislada, 3 repeticiones, con el arreglo final (intento 4) puesto | **Válido** — 0/3 escrituras, confirma consistencia |
| `gpt4o_t03_t14_fix3_regression.json` | T03+T14, con solo el intento 3 (primera versión del arreglo) puesto | **Evidencia de regresión** — T14 rompió aquí; no representa el estado final |
| `gpt4o_dispute_tasks_fix4_regression.json` | Las 12 tareas de `agent_tasks_v2.json` que tocan disputas, con el arreglo final (intento 4) | **Válido** — 11/12 match exacto; el T08 "mismatch" es benigno (ver informe) |

La corrida baseline (sin ningún arreglo, gpt-4o) y las de los intentos 1 y 2 (que no funcionaron)
no se guardaron como JSON — solo se observaron en terminal, y están transcritas en
`T08_ROOT_CAUSE_FIX.md`. El Postgres/venv local usados para todo esto se borraron al cerrar la
sesión; no queda infraestructura local persistente de esta prueba.
