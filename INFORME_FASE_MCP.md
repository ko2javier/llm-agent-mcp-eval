# Informe de la fase MCP — 05 ago 2026

Este documento cuenta la historia completa de la sesión: qué se construyó, por qué, cómo se
verificó, y — la parte que no estaba escrita en ningún sitio — **qué quedó a medias**. Es el punto
de entrada para entender el trabajo sin tener que reconstruirlo leyendo doce ficheros sueltos.

Para los números en limpio: [`results/RESULTADOS_MCP.md`](results/RESULTADOS_MCP.md). Este informe
añade el hilo narrativo y las deudas pendientes.

---

## 1. Punto de partida

La fase anterior (`RESULTADOS.md`) había dejado un agente Gemma 4 31B con 5 tools hardcodeadas,
15/15 tareas resueltas, 14/15 con la secuencia exacta esperada. Ese resultado, sin embargo, no
respondía dos preguntas que sí importan en producción:

1. **¿Cambia algo si las tools se sirven por MCP en vez de ir compiladas en el agente?** Es la
   diferencia entre "el agente conoce sus herramientas" y "el agente las descubre en runtime contra
   un servidor" — arquitecturalmente muy distinto, y nadie había medido si el modelo se comporta
   igual en los dos casos.
2. **¿Qué pasa cuando el catálogo crece?** Con 5 tools no se puede saber si el modelo confunde
   herramientas parecidas cuando hay 20 donde elegir. La literatura dice que la precisión cae a
   partir de 10–15 tools.

Esta fase se construyó para responder ambas, más una tercera que surgió sobre la marcha: si las
`annotations` de MCP (`destructiveHint`, etc.) sirven como mecanismo de seguridad de verdad o son
solo metadata decorativa.

## 2. Qué se construyó

- **`scripts/mcp_server.py`** — los mismos 5 tools de la fase anterior, expuestos por MCP
  (FastMCP, HTTP/streamable-http), con un flag `--profile` para servir 5, 12 o 20 tools y un flag
  `--annotations` para anunciar `readOnlyHint`/`destructiveHint`/`idempotentHint`.
- **`scripts/mcp_agent.py`** — el mismo bucle ReAct de `agent.py`, pero descubriendo las tools por
  `tools/list` en vez de importarlas. Añade `--reset-cmd` para resetear el ledger entre tareas
  (ver §4, deuda de aislamiento) y `_describe()`, la función que traduce las annotations MCP a texto
  dentro de la descripción de la tool porque **la API de function-calling de OpenAI no tiene ningún
  campo donde ponerlas** — es un hueco real del puente MCP → tool-calling clásico, no un descuido de
  este proyecto en particular.
- **`scripts/tools_extended.py`** — 15 tools nuevas (paginación, idempotencia, errores accionables)
  para poder escalar el catálogo de 5 a 20 sin inventar herramientas de relleno.
- **`sql/setup_mock_extended.sql`** — 5 tablas nuevas (disputas, suscripciones, autorizaciones...)
  que las 15 tools nuevas necesitan para tener estado real sobre el que operar.
- **`dataset/agent_tasks_v2.json`** (50 tareas) y **`dataset/TRAMPAS.md`** — un dataset de "tareas
  trampa": cada una construida para tentar al modelo a llamar la tool equivocada, con una categoría
  diagnosticable (`confusable_write`, `id_ambiguity`, `idempotency`, `must_refuse`...). El núcleo es
  `confusable_write`: cuatro tools que "deshacen" algo distinto (`initiate_refund`,
  `void_authorization`, `accept_dispute`, `cancel_subscription`) y que el lenguaje natural invita a
  confundir. Detalle tarea a tarea en `dataset/TRAMPAS.md`.
- **`scripts/score_runs.py`** — separa fallos baratos (leer el registro equivocado) de fallos caros
  (`wrong_write` / `harmful_write`: escribir donde no tocaba), porque en un sistema de pagos no
  cuestan lo mismo.
- **`scripts/validate_dataset.py`** y **`scripts/reset_ledger.sh`** — comprobaciones y utilidades que
  nacieron *después* de encontrar errores de diseño en el dataset (ver §4).

Infraestructura: todo corrió sobre una instancia Vast.ai alquilada (NVIDIA L40S 46GB, ~$0.75/h),
vLLM 0.26.0 sirviendo Gemma 4 31B IT (AWQ) con `--tool-call-parser gemma4`, dos virtualenvs
separados (`/venv/main` para vLLM, `/venv/mcp` para el servidor MCP) por un conflicto real de
dependencias (`mcp==2.0.0` que trae vLLM vs `mcp==1.29.0` que exige fastmcp).

## 3. Los seis resultados

Desarrollados con cifras en [`results/RESULTADOS_MCP.md`](results/RESULTADOS_MCP.md). En una frase
cada uno:

1. **MCP no cambia ni una decisión del modelo** frente a tools hardcodeadas — mismas secuencias de
   tool calls, +2,9% de sobrecoste en tokens/latencia.
2. **El catálogo no degrada precisión** de 5 a 20 tools (100% plano sobre las tareas comparables),
   pero **multiplica por 4,33× los tokens de prompt**.
3. Sobre el catálogo completo y las 50 tareas trampa, **todas las categorías salen perfectas salvo
   `confusable_write`** (8/9) — la única categoría diseñada específicamente para hacer fallar al
   modelo.
4. El único error caro (T08) es **de obediencia, no de selección de tool**: el modelo reembolsa una
   transacción con un chargeback ya abierto porque el usuario se lo pide explícitamente, pagando dos
   veces. Ocurre en los cuatro catálogos probados, en distintas formas.
5. **Las annotations de MCP no sirven como mecanismo de seguridad**: ponerlas realmente en el prompt
   cuesta +26% de tokens y T08 falla exactamente igual.
6. **`temperature 0` no es determinista en vLLM**: dos corridas idénticas del mismo perfil difieren
   en 3 de 50 tareas (siempre en reintentos, nunca en el veredicto final) — atribuible al batching
   dinámico del motor.

## 4. Cómo se llegó ahí — la parte que no sale en un README

El proceso no fue lineal. `POSTMORTEM.md` documenta 16 errores concretos con causa/impacto/lección;
aquí va el resumen de qué tipo de errores fueron y qué patrón los conecta, porque el patrón importa
más que cualquier error individual:

- **Cuatro números publicables que eran falsos** en algún momento del proceso, y se detectaron antes
  de que llegaran a un documento final:
  - Una "degradación del 93% al 26%" al crecer el catálogo que en realidad era el dataset pidiendo
    tools que no existían en el catálogo pequeño (E5) — *confirmaba la hipótesis de partida, que es
    justo lo que la hizo peligrosa*.
  - Una primera "corrección" (restringir a tareas resolubles) que seguía comparando conjuntos de
    dificultad distinta entre catálogos (E6).
  - Un "0 escrituras dañinas con 19 tools" que en realidad escondía que el modelo había cedido un
    chargeback de 120 USD porque la lista manual de `forbidden_tools` no había previsto esa forma
    concreta de perder dinero (E7).
  - Un "+14% de overhead" de MCP que en realidad comparaba dos GPUs distintas, no MCP contra
    hardcodeado (E9).
- **Tres tareas del dataset estaban mal diseñadas**, no el modelo: dos tareas contradictorias sobre
  la misma fila (E13), una tarea sin ningún camino de tools que la resolviera (E14), y un dataset con
  escrituras corriendo en secuencia contra la misma base sin reset entre tareas, contaminando el
  estado que leían tareas posteriores (E12).
- **Un bug real de puente** entre MCP y la API de tool-calling: las `annotations` no llegaban al
  modelo (E16) — a punto de publicarse como "el modelo ignora las annotations" cuando en realidad el
  modelo nunca las vio.
- **Una métrica con un falso positivo** todavía sin arreglar del todo: `harmful_write` marca como
  dañina cualquier escritura fuera de `expected_tools`, pero en tareas compuestas ("reembolsa X y
  cancela Y") donde una mitad falla legítimamente, la otra mitad se cuenta como error caro aunque sea
  exactamente lo que el usuario pidió (E15).

El patrón que conecta la mayoría: **enumerar a mano lo que debería derivarse de una regla**
(`forbidden_tools`, `expected_tools`) solo cubre los fallos que el diseñador ya imaginó. El modelo
encontró formas de fallar — y de tener razón — fuera de esas listas, dos veces.

## 5. Deudas — lo que quedó a medias

Esto es lo que no está resuelto, ordenado por lo que más limita la validez de las conclusiones:

### Deudas de validez del experimento

1. **N=1 modelo.** Todo lo anterior es sobre Gemma 4 31B AWQ exclusivamente. No hay forma de saber
   si T08 (el fallo de obediencia) o la curva plana de precisión son propiedades de este modelo o del
   diseño de las tools. Descartado por presupuesto, no por diseño — es la deuda que más pesa porque
   invalida cualquier generalización.
2. **Determinismo no resuelto, solo detectado.** Se sabe que `temperature 0` en vLLM no es
   determinista (3/50 tareas varían entre corridas idénticas) pero no se investigó *por qué* más allá
   de "el batching dinámico cambia la aritmética en punto flotante", ni se corrió suficientes
   repeticiones para dar un intervalo de confianza a ninguna de las cifras publicadas — todas son de
   una sola corrida (excepto la comparación de determinismo en sí).
3. **La métrica `harmful_write` tiene un falso positivo conocido y sin arreglar** (E15, arriba).
   El arreglo que se identificó pero no se implementó: separar `expected_tools` (camino correcto) de
   un campo nuevo `authorized_writes` (lo que el usuario autoriza, aunque falle), para que tareas
   compuestas no penalicen la mitad que sí se ejecutó correctamente.

### Deudas de seguridad / diseño de producto

4. **El hallazgo de seguridad no se implementó, solo se documentó.** Se demostró que las annotations
   de MCP no evitan T08 (resultado 5), y la conclusión — que la comprobación debe vivir en el
   servidor, no en el prompt — es correcta pero **no se construyó**: `initiate_refund` todavía no
   comprueba si existe una disputa abierta antes de ejecutar. El experimento diagnosticó el problema
   y no lo corrigió.
5. **Sin multi-servidor MCP.** No se probó tener dos servidores MCP activos a la vez, con colisión de
   nombres de tools ni descubrimiento dinámico entre ellos — un escenario realista en un agente que
   hable con más de un sistema.

### Deudas de proceso / infraestructura

6. **Validación de diseño posterior a la construcción, no anterior.** `validate_dataset.py` y
   `reset_ledger.sh` se escribieron *después* de tropezar con los errores que habrían evitado (E5,
   E10, E12). No están integrados como gate automático antes de lanzar una corrida — si alguien
   añade una tarea nueva al dataset mañana, nada le impide repetir E5, E13 o E14 salvo acordarse de
   correr el validador a mano.
7. **Sin CI ni regresión automática.** Todas las corridas fueron manuales, lanzadas y verificadas a
   mano sobre la instancia Vast. No hay ningún pipeline que vuelva a correr el golden set cuando
   cambie `tools.py`, `mcp_server.py` o el dataset.
8. **Coste solo parcialmente contabilizado.** Se sabe el $/h de la GPU (~$0.75) y el coste de la
   corrida de 15 tareas de la fase anterior ($0.0122), pero no hay un coste total agregado de toda la
   sesión (instalación + las ~12 corridas + reintentos) — dato que sí importaría para justificar esta
   forma de trabajar frente a alternativas.
9. **Gestión de secretos manual.** El token de Hugging Face vive en un fichero de texto plano
   (`hugging.txt`, fuera del repo) que se copia a mano a la instancia remota en cada sesión. Funciona,
   pero no hay rotación ni gestor de secretos — aceptable para un proyecto personal, no para nada más
   allá de eso.
10. **Sin pruebas de concurrencia.** El servidor MCP y el agente se probaron siempre con una tarea a
    la vez, en secuencia. No se sabe cómo se comporta `mcp_server.py` con llamadas concurrentes, ni si
    el reset del ledger entre tareas sería seguro si dos agentes corrieran a la vez.

### Deuda menor de higiene del dataset

11. **`agent_tasks_extended.json` (v1) se conserva sabiendo que es defectuoso** (E5: 36/50 tareas
    inejecutables con catálogo pequeño), solo porque tres resultados de la curva de determinismo
    (`curve_full_a.json` / `curve_full_b.json`) se midieron con él y no merecía la pena rehacer esa
    corrida. Cualquiera que abra el dataset sin leer `TRAMPAS.md` puede confundirlo con el bueno
    (`agent_tasks_v2.json`).

---

## Cómo se relaciona esto con el resto de los documentos

```
INFORME_FASE_MCP.md          <- estás aquí: la historia completa + las deudas
README.md                    <- qué es el repo, arquitectura, cómo correrlo
POSTMORTEM.md                <- los 16 errores con causa/impacto/lección, uno a uno
results/RESULTADOS_MCP.md    <- los 6 resultados de esta fase, solo cifras
results/RESULTADOS.md        <- resultados de la fase anterior (15 tareas, 5 tools), siguen válidos
results/NOTES.md             <- qué fichero .json de resultados usar para qué (válidos vs superados)
dataset/TRAMPAS.md           <- diseño de las 50 tareas trampa, una a una
```
