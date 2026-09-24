const elements = {
  appName: document.getElementById('app-name'),
  welcome: document.getElementById('welcome-text'),
  rooms: document.getElementById('rooms'),
  roomCount: document.getElementById('room-count'),
  leaveRoom: document.getElementById('leave-room'),
  users: document.getElementById('users'),
  onlineCount: document.getElementById('online-count'),
  profileName: document.getElementById('profile-name'),
  profileAvatar: document.getElementById('profile-avatar'),
  roomTitle: document.getElementById('room-title'),
  roomDescription: document.getElementById('room-description'),
  messages: document.getElementById('messages'),
  form: document.getElementById('chat-form'),
  input: document.getElementById('message')
};

let currentRoom = 'general';
let initialAssetVersion = null;
let lastMessagesSignature = '';
let requestRunning = false;

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function applyTheme(theme) {
  const variables = {
    accent: '--accent',
    background: '--background',
    sidebar: '--sidebar',
    panel: '--panel',
    text: '--text',
    muted: '--muted'
  };

  for (const [key, variable] of Object.entries(variables)) {
    if (theme[key]) {
      document.documentElement.style.setProperty(variable, theme[key]);
    }
  }
}

function roomName(roomId, rooms) {
  const room = rooms.find(item => item.id === roomId);
  return room ? room.name : roomId;
}

function renderRooms(state) {
  elements.roomCount.textContent =
    state.rooms.length + (state.rooms.length === 1 ? ' canal' : ' canales');

  elements.rooms.innerHTML = state.rooms.map(room => {
    const active = room.id === state.current_room ? ' active' : '';
    return (
      '<button class="room-button' + active + '" type="button" ' +
      'data-room="' + escapeHtml(room.id) + '">' +
        '<span><b>#</b> ' + escapeHtml(room.name) + '</span>' +
        '<small>' + Number(room.online || 0) + '</small>' +
      '</button>'
    );
  }).join('');

  elements.rooms.querySelectorAll('.room-button').forEach(button => {
    button.addEventListener('click', () => joinRoom(button.dataset.room));
  });
}

function renderUsers(state) {
  elements.onlineCount.textContent = state.users.length;
  if (!state.users.length) {
    elements.users.innerHTML =
      '<li class="no-users">Sin usuarios conectados</li>';
    return;
  }

  elements.users.innerHTML = state.users.map(user => (
    '<li>' +
      '<span class="user-avatar">' +
        escapeHtml(String(user.user).charAt(0).toUpperCase()) +
      '</span>' +
      '<span class="user-data">' +
        '<strong>' + escapeHtml(user.user) + '</strong>' +
        '<small>' +
          escapeHtml(roomName(user.room, state.rooms)) +
        '</small>' +
      '</span>' +
      '<span class="online-dot"></span>' +
    '</li>'
  )).join('');
}

function renderMessages(state) {
  const signature = JSON.stringify({
    room: state.current_room,
    messages: state.messages
  });
  if (signature === lastMessagesSignature) return;
  lastMessagesSignature = signature;

  if (!state.messages.length) {
    elements.messages.innerHTML =
      '<div class="empty-state">' +
        '<div class="empty-icon">#</div>' +
        '<h3>Inicio de ' +
          escapeHtml(state.current_room_name) +
        '</h3>' +
        '<p>Todavía no hay mensajes en esta sala.</p>' +
      '</div>';
    return;
  }

  elements.messages.innerHTML = state.messages.map(message => {
    if (message.type === 'system') {
      return (
        '<div class="notice system">' +
          escapeHtml(message.message) +
        '</div>'
      );
    }

    const initial = String(message.user || '?').charAt(0).toUpperCase();
    return (
      '<article class="message">' +
        '<div class="message-avatar">' + escapeHtml(initial) + '</div>' +
        '<div class="message-body">' +
          '<div class="message-meta">' +
            '<strong>' + escapeHtml(message.user) + '</strong>' +
            '<time>' + escapeHtml(message.time) + '</time>' +
          '</div>' +
          '<p>' + escapeHtml(message.message) + '</p>' +
        '</div>' +
      '</article>'
    );
  }).join('');

  elements.messages.scrollTop = elements.messages.scrollHeight;
}

async function apiRequest(path, options = {}) {
  const response = await fetch(path, options);
  if (response.status === 401) {
    window.location.href = '/login';
    throw new Error('Sesión terminada');
  }

  const contentType = response.headers.get('content-type') || '';
  if (!contentType.includes('application/json')) {
    throw new Error('El servidor no devolvió JSON');
  }

  const result = await response.json();
  if (!result.ok) {
    throw new Error(result.error || 'Operación no disponible');
  }
  return result;
}

async function joinRoom(room) {
  if (room === currentRoom) return;
  await apiRequest('/api/join', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({room})
  });
  lastMessagesSignature = '';
  await refresh();
}

async function leaveRoom() {
  await apiRequest('/api/leave', {method: 'POST'});
  lastMessagesSignature = '';
  await refresh();
}

async function refresh() {
  if (requestRunning) return;
  requestRunning = true;
  try {
    const state = await apiRequest('/api/state');

    if (initialAssetVersion === null) {
      initialAssetVersion = state.asset_version;
    } else if (initialAssetVersion !== state.asset_version) {
      window.location.reload();
      return;
    }

    currentRoom = state.current_room;
    document.title = state.config.app_name;
    elements.appName.textContent = state.config.app_name;
    elements.welcome.textContent = state.config.welcome;
    elements.profileName.textContent = state.username;
    elements.profileAvatar.textContent =
      String(state.username).charAt(0).toUpperCase();
    elements.roomTitle.textContent = state.current_room_name;
    elements.roomDescription.textContent =
      state.current_room === 'general'
        ? 'Canal para todos los usuarios.'
        : 'Conversación para quienes están dentro de esta sala.';
    elements.leaveRoom.hidden = state.current_room === 'general';
    elements.input.maxLength = state.config.max_message_length;
    elements.input.placeholder =
      'Mensaje en #' + state.current_room_name;

    applyTheme(state.config.theme || {});
    renderRooms(state);
    renderUsers(state);
    renderMessages(state);
  } catch (error) {
    console.error(error);
  } finally {
    requestRunning = false;
  }
}

elements.form.addEventListener('submit', async event => {
  event.preventDefault();
  const message = elements.input.value.trim();
  if (!message) return;

  try {
    await apiRequest('/api/send', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message})
    });
    elements.input.value = '';
    elements.input.focus();
    await refresh();
  } catch (error) {
    alert(error.message);
  }
});

elements.leaveRoom.addEventListener('click', () => {
  leaveRoom().catch(error => alert(error.message));
});

refresh();
setInterval(refresh, 800);
