# Bot de Telegram → Airtable

Hace dos cosas, las dos terminan en Airtable:

**Recetas de cocina.** Le compartes un video de **YouTube, TikTok, Instagram o
Facebook** y te regresa la receta transcrita y estructurada.

```
Compartes el video  →  texto + audio + cuadros  →  Claude arma la receta  →  Airtable
```

**Gastos dictados.** Le dictas o escribes un movimiento y lo registra en la tabla
`Master` de tu base **Atenea**, clasificado contra tus propios catálogos.

```
"350 de gasolina en la Gasolinera, Inbursa, ayer"  →  Atenea / Master
```

Captura el efectivo, que ningún estado de cuenta ve, en el momento en que lo
gastas — que es el único momento en que existe.

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

## Los gastos: cómo no ensuciar Atenea

Llena seis campos de `Master`: `Fecha`, `Forma de pago`, `Monto`, `Lugar`,
`Categoría` y `Detalles`.

El problema real no es extraer el gasto — es no empeorar el catálogo. `Lugar`
tiene ~190 opciones y `Categoría` ~54, ya con variantes acumuladas del mismo
concepto (`WALMART` / `Walmart`, `Súper` / `S´uper` / `Super`). Un bot con
`typecast` habilitado agregaría una variante más en cada dictado.

Tres decisiones evitan eso:

1. **Los catálogos se leen de Airtable en caliente**, no van escritos en el
   código. Agregas un lugar allá y el bot lo sabe en menos de 10 minutos, sin
   tocar nada aquí.
2. **Nunca se manda `typecast`.** El bot es incapaz de crear una opción o una
   forma de pago nueva, aunque quisiera.
3. **Lo que no empata se deja vacío, no se fuerza.** Si dictas un lugar que no
   está en tu lista, el movimiento se guarda igual con lo demás, el campo queda
   en blanco, y el aviso se escribe en `Detalles` y se te dice en Telegram. Un
   hueco que tú llenas es mejor que una categoría equivocada enterrada en tu
   contabilidad.

`Forma de pago` no es un desplegable sino un vínculo a la tabla `Sumandos`, así
que el nombre dictado se resuelve al ID del registro antes de escribir —
comparando sin acentos ni mayúsculas, para que "inbursa" encuentre "Inbursa".

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

## ⚠️ Dónde NO ponerlo

**No lo dejes en `~/Documents` ni en ninguna carpeta sincronizada** (iCloud,
Dropbox, Google Drive).

Se probó en carne propia: en `~/Documents` de una Mac, importar los módulos del
bot tardaba **419 segundos**; los mismos archivos en `~/` tardan **2.6**. El bot
no se veía roto — arrancaba, pero tardaba entre dos y siete minutos en empezar a
escuchar Telegram, así que parecía muerto.

Si el arranque se siente lento, mide antes de suponer:

```bash
python -u -c "import time; t=time.time(); import recipe_bot.bot; print(f'{time.time()-t:.1f}s')"
```

Arriba de 5 segundos, el problema es dónde vive la carpeta.

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
