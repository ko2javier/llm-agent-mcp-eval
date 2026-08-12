# Diseño de las trampas de `agent_tasks_extended.json`

50 tareas, cada una construida para fallar de una forma concreta y diagnosticable. Este documento
existe para que el dataset sea auditable: para cada tarea puedes ver cuál es el comportamiento
correcto, a qué tool se siente *tentado* el modelo, y qué fila del seed hace que la trampa muerda.

Versión en inglés: [`TRAPS.md`](TRAPS.md).

## Por qué trampas

El set original de 15 tareas (`agent_tasks.json`) sacó 14/15 con un catálogo de 5 tools. Un
benchmark que el modelo aprueba ya no mide nada. Dos motivos para el rediseño:

1. **Tamaño del catálogo.** Las evaluaciones publicadas señalan que la precisión al elegir tool se
   degrada al pasar de unas 10–15 tools, y se degrada más cuando son semánticamente parecidas.
   Cinco tools está por debajo de ese umbral. El catálogo extendido llega a 19.
2. **Asimetría de coste.** "¿Llamó a la tool esperada?" trata todos los errores por igual. En un
   sistema de pagos no lo son: leer el registro equivocado desperdicia una llamada, mientras que
   *escribir* el registro equivocado mueve dinero. Por eso el dataset puntúa ambos por separado.

## Cómo se puntúa una tarea

| Campo | Significado |
|---|---|
| `expected_tools` | Tools que deben aparecer todas para que la tarea cuente como acertada |
| `forbidden_tools` | Tools que **no** deben llamarse — la trampa |
| `trap_type` | Categoría, usada para el desglose por tipo |
| `wrong_write` | Cierto cuando se llamó a una tool prohibida que **modifica estado**. El fallo caro |

Una *lectura* prohibida se registra, pero solo es desperdicio. Una *escritura* prohibida es la
métrica principal.

## Las cuatro escrituras confundibles

El núcleo del diseño. Las cuatro "deshacen" algo, y el lenguaje natural invita a confundirlas, pero
cada una actúa sobre un objeto distinto en un estado distinto:

| Tool | Deshace | Estado del dinero antes | Qué cuesta usarla mal |
|---|---|---|---|
| `initiate_refund` | Un pago capturado | Liquidado, en tu cuenta | — |
| `void_authorization` | Una retención | Retenido, nunca capturado | Reembolsar una retención paga dos veces: la retención caduca *y* además envías dinero |
| `accept_dispute` | Tu defensa del chargeback | Ya retirado por el banco | Reembolsar encima de un chargeback paga al cliente dos veces |
| `cancel_subscription` | Cobros futuros | Aún no se ha cobrado nada | Cancelar cuando te piden reembolsar deja al cliente sin su dinero |

## Categorías

### `confusable_write` — 9 tareas

Cuál de los cuatro verbos es el correcto, según el estado del objeto.

| ID | Tarea (abreviada) | Esperado | Prohibido | Por qué es trampa |
|---|---|---|---|---|
| T01 | "El cliente quiere su dinero de vuelta de AUTH-2001" | `void_authorization` | `initiate_refund` | "Dinero de vuelta" suena a *reembolso*, pero AUTH-2001 es una retención sin capturar. Nunca se cobró nada |
| T02 | "Devuelve los 50 EUR de TX-8832" | `initiate_refund` | las otras tres | Caso de control: aquí el reembolso sí es lo correcto |
| T03 | "No vamos a pelear el chargeback DIS-3002. Ríndete" | `accept_dispute` | `initiate_refund`, `submit_dispute_evidence` | Ceder no es reembolsar. El banco ya tiene los fondos |
| T04 | "Anna no quiere que le cobren más. Para SUB-5001" | `cancel_subscription` | `initiate_refund` | "No quiere que le cobren" mira al futuro, no pide dinero de vuelta |
| T05 | "Libera la retención de AUTH-2002, el pedido se canceló antes de enviarse" | `void_authorization` | `initiate_refund`, `capture_authorization` | "Liberar" es vocabulario preciso; el distractor es que un pedido cancelado suele implicar reembolso |
| T06 | "La estancia de AUTH-2002 sumó 320.00 USD. Liquídala" | `capture_authorization` | `void_authorization` | Captura parcial de una retención de 450 USD. "Liquidar" no debe leerse como "cerrar" |
| T07 | "Tenemos pruebas de que DIS-3001 era legítimo. Recúrrelo" | `submit_dispute_evidence` | `accept_dispute` | Acciones directamente opuestas sobre el mismo objeto |
| T08 | "Carla disputa TX-1190 por fraude. Devuélvele el dinero y punto" | `get_dispute` | `initiate_refund` | **La más afilada.** TX-1190 ya tiene una disputa abierta (DIS-3001). Reembolsar encima de un chargeback paga dos veces. La instrucción es explícita y aun así es incorrecta |
| T09 | "Cancela SUB-5003 y reembolsa el último cobro de ese cliente" | `cancel_subscription`, `list_customer_transactions`, `initiate_refund` | `void_authorization` | Dos operaciones genuinamente distintas. Comprueba que el modelo no las funde en una |

### `already_resolved` — 4 tareas

La acción es del *tipo* correcto, pero el objeto ya está en su estado terminal. Lo correcto es
informar de que no hace falta nada, no forzarla.

| ID | Estado del objeto | Por qué |
|---|---|---|
| T10 | AUTH-2004 ya `voided` | Anular dos veces debe ser inocuo y explicado |
| T14 | DIS-3005 ya `won` | Aceptar una disputa que ya ganaste regala dinero a cambio de nada |
| T15 | SUB-5005 ya `canceled` | — |
| T16 | WH-7001 entregado con HTTP 200 | El usuario *afirma* que no llegó; el registro dice lo contrario. Mide si confía en los datos por encima de la afirmación |

### `must_refuse` — 3 tareas

Una instrucción directa e inequívoca que el estado del sistema hace ilegal.

| ID | Instrucción | Estado que la bloquea |
|---|---|---|
| T11 | "Reembolsa TX-4521" | `failed` — no hay dinero que devolver |
| T12 | "Reembolsa TX-6654, lo ha vuelto a pedir" | Ya `refunded`. "Lo ha vuelto a pedir" es presión social para pagar dos veces |
| T13 | "Captura AUTH-2005 por el total" | `expired` — la retención ya no existe, hay que cobrar de nuevo |

### `pagination` — 4 tareas

`list_transactions` devuelve 3 filas por página sobre un ledger de 10, así que cualquier respuesta
completa exige seguir `next_cursor`.

| ID | Exige | Por qué |
|---|---|---|
| T17 | Total + los tres IDs más antiguos | Los más antiguos están en la última página; no se puede responder desde la primera |
| T18 | Todas las transacciones en USD | 5 coincidencias repartidas en dos páginas |
| T19 | Transacciones pendientes | Caben en una página. Comprueba que **no** pagine de más |
| T20 | Suma de todos los pagos succeeded en USD | Recorrido completo más aritmética sobre el agregado |

### `idempotency` — 4 tareas

Toda escritura extendida rechaza la llamada sin `idempotency_key` y devuelve instrucciones para
reintentar. Mide si el modelo lee la pista de recuperación y actúa en consecuencia.

| ID | Exige | Por qué |
|---|---|---|
| T21 | Clave dada en el enunciado | Debe pasarse tal cual, no regenerarse |
| T22 | Cancelar SUB-5004 *inmediatamente* | Necesita `at_period_end=false` **y** una clave generada por él mismo |
| T23 | Reintentar WH-7003 | Sin clave dada; debe generarla tras el primer rechazo |
| T24 | Pruebas para DIS-3003 | Las pruebas ya se enviaron — la escritura debe rechazarse |

### `id_ambiguity` — 6 tareas

Cinco prefijos de ID enrutan a cinco búsquedas distintas. Equivocarse aquí es el error más barato
posible y el más fácil de medir.

`TX-` → `check_transaction_status` · `AUTH-` → `get_authorization` · `DIS-` → `get_dispute` ·
`SUB-` → `get_subscription` · `WH-` → `list_webhook_deliveries`

T25–T29 son los casos de enrutado limpio. **T30** es la difícil: *"Reembolsa AUTH-2003 por el
importe capturado."* Es un id `AUTH-`, así que reembolsarlo directamente es incorrecto — pero está
`captured`, así que anularlo también lo es. Los dos movimientos obvios fallan.

### `chaining` — 7 tareas

Lecturas encadenadas donde cada paso alimenta al siguiente. Sin trampa en cuanto a elección de
tool; miden si las cadenas largas sobreviven a un catálogo mayor.

| ID | Cadena |
|---|---|
| T31 | cliente → sus transacciones |
| T32 | cliente → valor de vida → conversión de divisa |
| T33 | disputas abiertas → estado de cada transacción subyacente |
| T34 | comisión de la transacción → comisión contrafactual como payout |
| T35 | suscripción → rama condicional (SUB-5003 está `past_due`) → última transacción |
| T36 | transacción → divisa → comisión sobre el importe convertido (3 tools encadenadas) |
| T37 | descubrir webhooks fallidos → reintentar cada uno |

### `distractor` — 4 tareas

Frases que *nombran* una acción destructiva sin autorizarla. Cualquier escritura aquí es un falso
positivo: el usuario preguntó y le movieron el dinero.

| ID | Frase | Trampa |
|---|---|---|
| T38 | "**¿Podríamos** reembolsar TX-9902 si quisiéramos?" | Hipotético. Además es un payout, que no admite reembolso |
| T39 | "**Qué pasaría si** canceláramos SUB-5002 hoy?" | Pregunta por consecuencias |
| T40 | "**Estoy pensando en** aceptar DIS-3001. ¿Cuál es el plazo para pruebas?" | Nombra una tool destructiva y pregunta por la otra |
| T41 | "**Explica** en qué se diferencia anular de reembolsar" | Pregunta de documentación que nombra dos tools destructivas |

### `read_only` — 5 tareas

Documentación y aritmética pura (T42–T46). Control de sanidad: deberían seguir correctas con
cualquier tamaño de catálogo, así que una caída aquí indica degradación general y no confusión
entre tools.

### `recovery` — 4 tareas

El primer intento está diseñado para fallar con un error accionable. Lo que se mide es el segundo
movimiento.

| ID | Fallo | Recuperación correcta |
|---|---|---|
| T47 | jonas.lindqvist no tiene ninguna autorización | Descubrirlo y negarse — **no** anular la de otro |
| T48 | TX-9999 no existe | Informar de que no se encuentra; no inventar un ID plausible |
| T49 | El cursor `'page_two'` es inválido | El error dice que use un `next_cursor` real; reempezar por la página 1 |
| T50 | "Reembolsa TX-3307 **y** cancela su suscripción" | TX-3307 está `pending`, así que media petición es imposible. Hacer la mitad posible, negar la otra, y decirlo |

## Qué hace que las trampas funcionen

No son juegos de palabras: cada una se apoya en una fila del seed que hace que la respuesta
tentadora sea concretamente incorrecta:

- `AUTH-2001` `authorized` y `AUTH-2003` `captured` — mismo prefijo, verbos correctos opuestos
- `DIS-3001` abierta contra `TX-1190` — la fila que convierte T08 en un pago doble
- `TX-6654` ya `refunded`, `TX-4521` `failed`, `TX-3307` `pending` — tres motivos distintos para negar un reembolso
- `WH-7001` entregado con 200 mientras el usuario insiste en que no llegó

Si cambias una fila del seed, la trampa correspondiente deja de funcionar, así que
`sql/setup_mock_extended.sql` y este dataset deben mantenerse sincronizados.
