# Alcance vigente: dashboard web de escritorio primero

Fecha: 2026-10-20. Estado: DECISION DEL USUARIO VIGENTE.
ID: SCOPE-DESKTOP-FIRST-20261020.

## Prioridad y precedencia
El desarrollo actual se concentra en el dashboard V2 web de escritorio y el
flujo funcional del bot. Esta decision sustituye requisitos anteriores de
desarrollo o aceptacion movil, incluidos los contenidos en prompts, disenos,
backlogs y handoffs historicos. No modifica estrategias, costes ni gates.

## Trabajo aplazado
- Interfaces y optimizaciones especificas para telefonos/tablets.
- QA, capturas y criterios de aceptacion a 360/390 px o equivalentes moviles.
- Aplicacion movil, Flutter, PWA, notificaciones y acceso remoto desde telefono.
- Dependencias o servicios incorporados exclusivamente para esas funciones.

Movil queda DEFERRED / FUERA DEL ALCANCE ACTUAL; no es un bloqueo para aceptar
una entrega de escritorio. No dedicarle nuevas tareas ni pruebas de layout.
Conservar codigo, pruebas y evidencias historicas: no borrarlos ni reescribir
historia. El responsive existente puede permanecer; no se promete su calidad
ni se exige corregirlo ahora. Accesibilidad y usabilidad en escritorio siguen
vigentes, incluida la navegacion por teclado.

## Objetivo funcional de escritorio
Priorizar seleccion y evidencia causal, decision versionada, simulacion paper,
gestion, cierre, persistencia/exportacion y revision posterior, reutilizando
el controlador, motor, fuentes y V2 existentes. Los graficos de operaciones
deben mostrar velas reales, frescura, entradas/fills simulados, protecciones y
cierres segun los eventos del motor; el frontend no decide operaciones.
Estas capacidades son el objetivo, no una declaracion de implementacion.

## Reapertura futura de movil
Solo despues de completar y aceptar explicitamente el alcance funcional de
escritorio acordado, el usuario podra autorizar una fase movil separada.
Flutter es una opcion futura preferida por el usuario, no una implementacion
actual aprobada. Evaluar entonces una app conectada mediante contratos/API al
backend existente, sin duplicar decisiones ni controles de riesgo.
Pruebas aprobadas, trazabilidad y evidencia funcional de escritorio deben
sostener la aceptacion; este documento no declara rentabilidad ni avanza gates.

## Documentacion y cierre de esta decision
Instruciones de alcance en AGENTS, WORKFLOW, TASK_QUEUE y skill dashboard-v2;
DECISIONS conserva el registro append-only y el diseno V2 pausa el requisito.
Los documentos CURRENT_STATE, FEATURE_BACKLOG y PAPER_LAB_PLAN estaban siendo
editados por el agente responsable y no se sobrescriben en este cambio.
En su cierre, el responsable debe reconciliarlos con esta decision, sin
reabrir trabajo movil. La evidencia movil anterior sigue siendo historica.
