CHAT CENTRALIZADO EN TIEMPO REAL
================================

QUE CAMBIA
- Solo la computadora de Angel ejecuta Python.
- Todos abren http://192.168.102.5:5000.
- Cada persona escribe su nombre al entrar.
- Hay General, Sala 1, Sala 2 y Sala 3.
- Usuarios, mensajes, salas y colores se actualizan para todos.
- Si cambia index.html, style.css o app.js, los navegadores se recargan solos.

INSTALACION
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

EJECUCION
python app.py

ABRIR EN LA COMPUTADORA DEL SERVIDOR
http://127.0.0.1:5000

ABRIR EN LAS COMPUTADORAS DEL SALON
http://192.168.102.5:5000

CAMBIAR COLORES O SALAS
Editar config.json y guardar. Los cambios aparecen en menos de un segundo.

CAMBIAR HTML, CSS O JAVASCRIPT
Editar templates/index.html, static/style.css o static/app.js y guardar.
Los navegadores abiertos se recargan automaticamente.

NOTA
Esta version web centralizada es una mejora adicional. Conserva por separado
la practica TCP original si el profesor exige mostrar nodos Flask locales.
