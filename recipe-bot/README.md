# Bot de Telegram → Airtable

Hace dos cosas, las dos terminan en Airtable:

**Recetas de cocina.** Le compartes un video de **YouTube, TikTok, Instagram o
Facebook** y te regresa la receta transcrita y estructurada.

```
Compartes el video  →  texto + audio + cuadros  →  Claude arma la receta  →  Airtable
```

**Gastos dictados.** Le dictas o escribes un gasto y lo registra clasificado.

```
"350 de gasolina, tarjeta, ayer"  →  Claude lo clasifica  →  tabla Gastos
```

Los gastos aterrizan en Airtable, no en el xlsx de Atenea: así revisas antes de
que entren a la contabilidad, y el efectivo —que ningún estado de cuenta ve—
queda capturado en el momento. De ahí los absorbe la conciliación mensual.

## Por qué un bot de Telegram

El share sheet del iPhone deja mandar un Reel o un TikTok a Telegram **como
archivo de video, no como link**. Eso elimina el problema más frágil del
proyecto — el scraping de Instagram y Facebook — y funciona igual desde el
teléfono, el iPad o la Mac. Sin App Store, sin cuenta de desarrollador, sin
extensión que mantener.

Los adaptadores por link son la comodidad; mandar el archivo es la red de
seguridad. Si mañana una plataforma cambia algo y se rompe un adaptador, el
sistema no se cae.

## Cómo saca la receta

Tres fuentes, y el orden importa porque no cuestan lo mismo:

| Fuente | Costo | De dónde sale |
|---|---|---|
| Texto del post | Gratis | Descripción de YouTube, caption de TikTok (vía oEmbed público), texto del post en Facebook |
| Subtítulos | Gratis | Los que ya publicó la plataforma (YouTube casi siempre tiene) |
| Audio transcrito | ~$0.006/min | Whisper, solo si no había subtítulos |
| Cuadros del video | ~$0.04 | Muestreo por cambio de escena + visión |

**Escala solo cuando hace falta.** Primera pasada: nada más texto. El modelo
reporta su propia confianza; si quedó completa, ahí termina y nunca se baja el
video. Si quedó coja, entonces sí se baja, se transcribe y se muestrean cuadros.

En YouTube la primera pasada casi siempre basta. En TikTok casi nunca: el audio
suele ser música y la receta está sobreimpresa en pantalla, así que ahí el
análisis de cuadros no es un complemento, es el canal principal.

## Lo que necesitas

1. **Un bot de Telegram** — escríbele a [@BotFather](https://t.me/BotFather),
   `/newbot`, y te da un token.
2. **Tu user id de Telegram** — escríbele a [@userinfobot](https://t.me/userinfobot).
3. **Una API key de Anthropic** — [console.anthropic.com](https://console.anthropic.com).
4. **Un Personal Access Token de Airtable** —
   [airtable.com/create/tokens](https://airtable.com/create/tokens), con scopes
   `data.records:write` y `schema.bases:write`, con acceso a tu base.
5. *(Opcional)* Una key para transcribir audio: OpenAI o Groq. Sin esto el bot
   sigue funcionando, pero pierde los videos narrados que no traen subtítulos.

También necesitas **ffmpeg** y **Python 3.11+** en la máquina donde corra.

## Instalación

```bash
cd recipe-bot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
$EDITOR .env            # llena los tokens

# Crea la tabla "Recetas" con el esquema correcto (es idempotente)
python scripts/setup_airtable.py

python -m recipe_bot
```

El `AIRTABLE_BASE_ID` es el `app...` que aparece en la URL cuando abres tu base
en el navegador.

## Uso

Abre el chat de tu bot y:

- **Pega una liga** de YouTube, TikTok, Instagram o Facebook → receta.
- **O comparte el video directo** desde la app (Compartir → Telegram → tu bot).
- **O dicta/escribe un gasto** → registro clasificado.

Cualquier mensaje que traiga una liga se trata como video; cualquier otro, como
gasto. Las **notas de voz** funcionan para las dos cosas: se transcriben y se
rutean igual que si las hubieras escrito.

Con dictado, el bot siempre te enseña primero lo que entendió (`🎙 «...»`) antes
de mostrarte el registro. No es adorno: es cómo detectas que Whisper oyó
"trescientos" donde dijiste "trece".

Si Instagram o Facebook rechazan el link, el bot te lo dice y te pide el archivo.
Para saltarte eso de raíz, puedes poner un `COOKIES_FILE` con cookies de sesión
en formato Netscape — funciona, pero se rompe cada tantas semanas y va contra los
términos de servicio de esas plataformas. Mandar el archivo es más estable.

## Los gastos

El bot clasifica contra las opciones que **ya existen** en tu tabla: 12
categorías, 3 ciudades, 4 formas de pago. Esas listas viven como tipos `Literal`
en `models.py`, así que **el modelo no puede inventar una categoría nueva** — no
es una instrucción del prompt que pueda ignorar, es el esquema que valida su
respuesta. Y se guarda sin `typecast`, para que el bot tampoco pueda crear
opciones nuevas en Airtable por accidente.

Lo que no le dictaste (ciudad, forma de pago) se supone con un default sensato y
queda anotado en `Notas` del registro, para que después sepas qué revisar.

Si agregas una categoría en Airtable, agrégala también a `CategoriaGasto` en
`recipe_bot/models.py`.

## La tabla de recetas en Airtable

`scripts/setup_airtable.py` crea estos campos:

`Nombre` · `Plataforma` · `URL` · `Autor` · `Porciones` · `Tiempo (min)` ·
`Ingredientes` · `Preparación` · `Notas` · `Kcal / porción` · `Proteína (g)` ·
`Carbos netos (g)` · `Grasa (g)` · `Keto` · `Adaptación keto` · `Tags` ·
`Confianza` · `Agregada`

Los macros y el campo `Keto` son estimaciones del modelo a partir de los
ingredientes y las porciones — sirven para filtrar y comparar, no como cálculo
nutricional. Con esos campos puedes armar vistas del tipo *"más de 30 g de
proteína, menos de 10 g de carbos netos, menos de 20 minutos"*.

`Confianza` y las advertencias en `Notas` te dicen cuándo el modelo tuvo que
reconstruir a partir de fragmentos. **El bot nunca inventa cantidades**: si no se
dicen ni se ven, deja el campo vacío y lo anota en `Notas`.

## Costos

Con `claude-opus-5` (el default):

| | Por receta |
|---|---|
| YouTube con buena descripción (una sola pasada) | ~$0.05 |
| TikTok / Reel con cuadros (dos pasadas) | ~$0.09 |
| Peor caso | ~$0.15 |
| Transcripción de audio | $0.006/min (OpenAI) · ~$0.001/min (Groq) |
| Hosting | ~$5/mes |

Si le pones `ANTHROPIC_MODEL=claude-sonnet-5` baja como a la mitad, con algo
menos de precisión leyendo texto sobreimpreso borroso.

## Despliegue

```bash
docker build -t recipe-bot .
docker run -d --restart unless-stopped --env-file .env recipe-bot
```

La imagen ya trae ffmpeg. Sirve igual en Railway, Fly.io o cualquier VPS: es un
proceso de larga vida que hace long polling, no necesita puerto abierto ni
dominio ni webhook.

## Limitaciones conocidas

- **Un video a la vez.** Es deliberado: para un solo usuario es más simple y más
  fácil de depurar que una cola. Si mandas tres seguidos, se forman.
- **Telegram solo deja bajar archivos de hasta 20 MB** por bot. Arriba de eso hay
  que mandar la liga.
- **Videos de más de 15 minutos no se bajan** para muestrear cuadros; se resuelven
  con descripción y subtítulos, que a esa duración casi siempre existen. Se ajusta
  con `max_video_seconds` en `config.py`.
- **Instagram y Facebook por link dependen de que el post sea público.** Es la
  parte frágil por diseño ajeno, no por diseño propio.
- Los macros son estimaciones, no análisis de laboratorio.

## Desarrollo

```bash
pip install -r requirements-dev.txt
python -m pytest tests -q
```

Las 50 pruebas corren sin red y sin ffmpeg: cubren el parseo de subtítulos, el
ruteo por plataforma, la construcción de comandos de ffmpeg, el payload de
Airtable, el formateo del mensaje y —lo más importante— la lógica de cuándo
escalar a bajar el video.

### Agregar una plataforma

Un archivo en `recipe_bot/resolvers/` con `matches()`, `resolve()` y
`fetch_media()`, más una línea en `construir()`. De ahí para abajo el pipeline
(transcripción, cuadros, Claude, Airtable) es el mismo para todas.

```
recipe_bot/
├── bot.py              Telegram: long polling, sin framework
├── config.py           Variables de entorno
├── models.py           Esquema de la receta (= contrato de salida de Claude)
├── resolvers/          Un archivo por plataforma + el registro
├── pipeline/
│   ├── run.py          Orquestador y lógica de escalado
│   ├── extract.py      La llamada a Claude
│   ├── frames.py       Muestreo por cambio de escena
│   └── audio.py        ffmpeg + Whisper
└── storage/airtable.py
```

## Seguridad

`TELEGRAM_ALLOWED_USERS` es **obligatorio** y el bot no arranca sin él. Un token
de Telegram es descubrible, y sin lista blanca cualquiera que dé con tu bot
gastaría tus créditos de API.

El contenido de los videos se trata como datos, no como instrucciones: el prompt
le dice explícitamente al modelo que ignore cualquier orden que venga dentro de
un caption o una transcripción.
