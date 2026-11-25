# PintaYa 0.01

Programa de pintura portable para niños (desde 2 años). Abre cualquier dibujo en blanco y negro
(jpg, jpeg, jpe, jfif, png, bmp, dib, gif, tif, heic, pdf) o una captura pegada con Ctrl+V,
lo prepara automáticamente y el bote de pintura rellena cada zona hasta el borde negro.

## Novedades 0.01
- **Gotero**: copia el color real de cualquier punto (también de imágenes pegadas). Guarda los últimos 12 en "Muestras".
- **Zoom**: Alt + rueda. Zoom máximo = lienzo de hasta 8192 px por lado (8K). Con zoom cercano aparecen barras de desplazamiento; rueda = vertical, Ctrl + rueda = horizontal.
- **Tamaño del lienzo**: arrastra las 8 asas (esquinas y puntos medios del borde), como en Paint. Máximo 8192 px por lado.
- **Pluma sobre las líneas**: solo la pluma dibuja encima del contorno y sirve para cerrar huecos; el bote respeta lo dibujado con la pluma.
- **Selección** libre / cuadro / círculo: mover (arrastrar), Cortar (Ctrl+X), Copiar (Ctrl+C), Borrar (Supr), fijar (clic fuera o Intro). Ctrl+Z mientras se mueve cancela el movimiento.
- **Pegar**: en un lienzo vacío la captura se procesa como dibujo; si ya hay un dibujo, se pega como imagen de referencia (sin procesar, a la derecha del dibujo) para usar el gotero. "Insertar" hace lo mismo desde un archivo. "Nuevo" vacía el lienzo.

## Uso
- Abrir (Ctrl+O) · Pegar captura (Ctrl+V) · Guardar PNG/JPG (Ctrl+S)
- Atrás (Ctrl+Z) / Adelante (Ctrl+Y)
- Herramientas: Bote, Pluma, Resaltador, Borrador, Pincel, Gotero + 4 grosores por herramienta
- 48 colores (4 filas x 12) y botón "+" para un color personalizado
- Las líneas negras quedan por encima del color: el niño no puede estropear el contorno (solo la pluma dibuja encima).
- "Detectar líneas" (barra inferior): si una imagen muy clara/oscura no se detecta bien, muévelo.

## Crear el .exe portable (Windows)
1. Instalar Python 3.10+ (solo en el equipo donde se compila).
2. Doble clic en `build.bat` -> `dist\PintaYa.exe`.
   (Alternativa sin instalar nada: subir esta carpeta a GitHub y ejecutar la acción "Build PintaYa.exe".)
3. Copiar `PintaYa.exe` a un pendrive o carpeta y ejecutar: no pide administrador.

## Estructura
- `engine.py`: procesamiento (separa líneas y color, regiones, relleno, trazos, historial). Sin interfaz.
- `app.py`: interfaz Tkinter.
