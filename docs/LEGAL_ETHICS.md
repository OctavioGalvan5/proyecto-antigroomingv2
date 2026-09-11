# Marco legal y ético

> Este documento **no reemplaza asesoramiento legal**. Antes de operar públicamente, un abogado especializado en derechos del niño y datos personales debe revisar el sistema.

## Contexto legal argentino relevante

### Ley 26.061 — Protección Integral de los Derechos de Niñas, Niños y Adolescentes
- **Art. 10**: Derecho a la dignidad y a un desarrollo pleno.
- **Art. 22**: Derecho a la intimidad. NNA (Niños, Niñas y Adolescentes) tienen derecho a que se respete su vida privada.
- **Art. 24**: Derecho a opinar y ser oído en todos los asuntos que los afecten.

**Implicancia**: aunque los padres tienen responsabilidad parental (patria potestad), la vigilancia total sin conocimiento del NNA colisiona con el art. 22 y 24. El sistema debe **informar al menor** y **darle capacidad de comprender** qué se monitorea.

### Ley 25.326 — Protección de Datos Personales
- Los mensajes de WhatsApp constituyen datos personales (y datos sensibles cuando revelan orientación sexual, salud, etc.).
- Se requiere **consentimiento informado** para el tratamiento.
- Un menor de edad puede prestar consentimiento cuando cuente con "madurez suficiente" (art. 26 CCyC). En caso contrario, lo hace el representante legal, pero eso no exime de informar al menor.

### Código Civil y Comercial
- **Art. 26**: Los adolescentes (13-16) tienen aptitud para decidir por sí sobre actos que no comprometen su estado de salud ni provocan riesgo grave; los mayores de 16 son considerados adultos para decisiones sobre su cuerpo.
- **Art. 638-641**: Responsabilidad parental. Los padres deben orientar y proteger, pero también respetar la autonomía progresiva del hijo.

### Ley 26.904 — Grooming (Código Penal art. 131)
- Tipifica como delito el contacto con menores por medios electrónicos con fines sexuales.
- Este sistema es una herramienta preventiva/de detección; **no reemplaza la denuncia** cuando corresponde. El material que se muestre al padre debe permitirle actuar (denunciar en fiscalía).

## Principios operativos del sistema

### 1. Consentimiento del menor documentado
Al vincular una cuenta:
- Se muestra al menor una pantalla en su celular (idealmente escaneando un QR con explicación previa que el padre le muestra).
- Lenguaje claro, adaptado a la edad. Nada de letra chica.
- Debe tildar activamente: "Entiendo qué se está monitoreando y acepto".
- Se persiste un `ConsentRecord` con timestamp, IP, user agent y hash del texto que aceptó.

### 2. Los padres NO ven la conversación completa
Del principio de mínima exposición:
- El padre ve la lista de `RiskEvent` con: contacto involucrado, severidad, razones textuales de la IA, y **un extracto acotado** (los mensajes que dispararon la alerta, no toda la conversación).
- El padre puede solicitar ver más contexto explícitamente, y esa acción queda auditada.

### 3. El menor puede consultar y revocar
- Endpoint `/mi-monitoreo?token=...` (link único que el menor recibe al aceptar). Le permite ver:
  - Qué se está monitoreando.
  - Cuándo se generó la última alerta (sin contenido).
  - Un botón "solicitar desvinculación" que envía notificación al padre y al equipo del producto.

### 4. Retención mínima
- Mensajes: **30 días** por default. Después: se conserva el hash y metadatos, no el contenido.
- RiskEvents: 1 año.
- Consentimientos: se conservan mientras la cuenta exista + 5 años (obligación de acreditar consentimiento ante autoridad si se requiere).

### 5. Sin cesión a terceros
- No compartimos mensajes con nadie salvo:
  - Requerimiento judicial válido.
  - El propio padre titular de la cuenta.

### 6. Sin publicidad ni analytics de contenido
- El contenido de los mensajes **no** se usa para publicidad, entrenamiento de modelos, ni analytics.
- Solo el mínimo indispensable de telemetría técnica (latencia, errores).

## Textos de consentimiento

### Para el padre (al crear cuenta)
Ver [DECISIONS.md ADR-0002](DECISIONS.md) para versión definitiva.

Borrador:
> Al usar este servicio declaro que:
> - Soy responsable legal del menor cuya cuenta voy a vincular.
> - He conversado con el menor sobre este monitoreo y voy a mostrarle la pantalla de consentimiento en su dispositivo.
> - Entiendo que este sistema **no reemplaza** el diálogo con mi hijo/a ni la denuncia policial ante hechos concretos.
> - Entiendo que la detección por IA puede tener falsos positivos y falsos negativos.

### Para el menor (al escanear el QR)
Borrador:
> Hola. Tus papás activaron una herramienta que va a leer los mensajes de WhatsApp que te lleguen. La herramienta no lee tus mensajes uno por uno, sino que busca **señales de peligro**: gente que quiera hacerte daño, pedirte fotos, o mantener secretos con vos.
>
> **Qué se lee:** mensajes que te llegan (texto). Por ahora no audios ni imágenes.
> **Qué ven tus papás:** solo alertas si el sistema detecta algo raro. NO ven todas tus conversaciones.
> **Cuánto se guarda:** los mensajes se borran a los 30 días.
> **Podés pedir que se apague:** entrando a este link cuando quieras.
>
> Si algo no te queda claro, pedile a tus papás que te expliquen antes de aceptar.
>
> [ ] Entendí y acepto.

## Casos borde a resolver antes de producción

- **Menor de <13 años**: WhatsApp prohíbe menores de 13 en sus ToS. Si el target del producto son <13, el sistema debe advertir al padre. Ver [ROADMAP.md](ROADMAP.md).
- **Adolescente que se niega a aceptar**: el sistema no puede activarse. Diseñar UX que evite forzar.
- **Cuenta compartida (celular familiar)**: si el WhatsApp lo usan varias personas, el consentimiento debe cubrirlas o el sistema debe negarse.
- **Denuncia obligatoria**: si el sistema detecta algo cuya gravedad supera "alerta al padre" (por ejemplo, contenido de abuso), qué obligación tenemos. **Pendiente asesoramiento**.
