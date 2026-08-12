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
