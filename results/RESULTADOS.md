# Resultados — Agente Gemma 4 31B, golden set de 15 tareas (01 ago 2026)

*(Traducción al español de `RESULTS.md`, que es la versión original/autoritativa. Mismos datos, mismas cifras.)*

**Instancia:** Vast.ai, 1× RTX 6000 Ada (48GB), $0.7493/h. vLLM 0.26.0, `--enable-auto-tool-choice --tool-call-parser gemma4` (sintaxis nativa de tool-calling de Gemma 4).

**Titular: 15/15 tareas completadas con una respuesta final correcta y sin alucinaciones. 14/15 coinciden con la secuencia exacta de tools esperada en el golden set.**

| Métrica | Valor |
|---|---|
| Tareas | 15 |
| Coincidencia estricta de secuencia de tools | 14/15 |
| Tocó el tope de MAX_TURNS (6) sin terminar | 0/15 |
| Latencia media | 3.92s |
| Turnos medios (idas y vueltas al LLM) | 2.3 |
| Coste GPU total de las 15 tareas | $0.0122 |

## La única "discrepancia" (A07) no es realmente un fallo

Tarea: *"Please refund transaction TX-7743."* Tool esperada: `initiate_refund`. Lo que hizo el modelo en realidad: llamó primero a `check_transaction_status`, vio `status: "failed"`, y respondió explicando que la transacción no se puede reembolsar — **sin llegar a llamar nunca a `initiate_refund`**.

Eso es, si acaso, mejor comportamiento del esperado: el modelo usó la información disponible para predecir que la llamada fallaría y la evitó, en vez de llamar a una tool que podía razonar que daría error. La métrica estricta de "¿llamó a la tool esperada?" no captura ese matiz — vale la pena tenerlo en cuenta al diseñar la evaluación de agentes con tools en general, no solo aquí.

## Otros comportamientos destacables

- **A02, A12** llamaron a `check_transaction_status` antes de `initiate_refund` aunque la tarea no pedía explícitamente comprobar el estado — el modelo verifica el estado antes de actuar sobre él por defecto. Buen instinto para una tool que cambia datos reales (simulados).
- **A06, A09** llamaron a la misma tool dos veces en un turno con argumentos distintos (`calculate_fees` para payment vs payout; `rag_lookup` con la pregunta reformulada) — comportamiento correcto, no un bug, simplemente el modelo dividiendo una pregunta compuesta en llamadas separadas.
- **A11, A15** activaron ambas las reglas de negocio de error de las tools (reembolsar un payout, reembolsar una transacción ya reembolsada) y el modelo mostró el error al usuario correctamente en vez de fingir que había tenido éxito.
- Se encontró y corrigió un artefacto del chat template durante el smoke test: el marcador interno `<|channel>thought...<channel|>` de Gemma 4 se filtraba al campo `content` visible en vez de ser descartado. Se parcheó con un `strip` por regex en `agent.py` (`clean_answer()`) — un hallazgo real de esta combinación específica de modelo/parser, no un problema genérico de vLLM.

## Qué demuestra esto y qué no

**Demuestra:** el tool-calling nativo funciona de punta a punta contra Gemma 4 31B AWQ vía vLLM, el agente elige la(s) tool(s) correcta(s) para cada tarea, encadena varias tools correctamente dentro de un turno o entre turnos, y maneja errores reportados por las tools de forma sensata en vez de alucinar un éxito.

**No demuestra:** comparación entre modelos (solo se probó uno, a propósito — ver README), robustez ante frases ambiguas/adversariales, ni comportamiento con un `MAX_TURNS` más alto o planes multi-paso más complejos que los que ejercita este set de 15 tareas.
