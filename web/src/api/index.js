const j = async (res) => {
  if (!res.ok) {
    let msg = res.statusText
    try { msg = (await res.json()).detail || msg } catch {}
    throw new Error(msg)
  }
  return res.json()
}

export const api = {
  books: () => fetch('/api/books').then(j),
  upload: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return fetch('/api/books/upload', { method: 'POST', body: fd }).then(j)
  },
  pages: (book) => fetch(`/api/books/pages?book=${encodeURIComponent(book)}`).then(j),
  bookFile: (book) => `/api/books/file?book=${encodeURIComponent(book)}`,
  deleteBook: (book) => fetch(`/api/books?book=${encodeURIComponent(book)}`, { method: 'DELETE' }).then(j),
  deleteOutput: (name) => fetch(`/api/output?name=${encodeURIComponent(name)}`, { method: 'DELETE' }).then(j),
  startTask: (body) => fetch('/api/task/start', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  }).then(j),
  taskStatus: () => fetch('/api/task/status').then(j),
  cancelTask: () => fetch('/api/task/cancel', { method: 'POST' }).then(j),
  clearTask: () => fetch('/api/task/clear', { method: 'POST' }).then(j),
  logsList: () => fetch('/api/logs/list').then(j),
  logs: (name, lines = 300) => fetch(`/api/logs?name=${encodeURIComponent(name)}&lines=${lines}`).then(j),
  glossary: () => fetch('/api/glossary').then(j),
  saveGlossary: (content) => fetch('/api/glossary', {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content }),
  }).then(j),
  genGlossary: (book, pages) => fetch('/api/glossary/generate', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ book, pages }),
  }).then(j),
  output: () => fetch('/api/output').then(j),
  jobs: () => fetch('/api/jobs').then(j),
  buildFinal: (body) => fetch('/api/postprocess/build-final', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  }).then(j),
  rewriteToc: (body) => fetch('/api/postprocess/rewrite-toc', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  }).then(j),
  addBookmarks: (body) => fetch('/api/postprocess/bookmarks', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  }).then(j),
  env: () => fetch('/api/env').then(j),
  keys: () => fetch('/api/keys').then(j),
  addKey: (name, key) => fetch('/api/keys/add', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, key }),
  }).then(j),
  deleteKey: (id) => fetch(`/api/keys/${encodeURIComponent(id)}`, { method: 'DELETE' }).then(j),
}
