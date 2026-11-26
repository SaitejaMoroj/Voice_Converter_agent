import { spawn } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const frontendDir = path.dirname(path.dirname(fileURLToPath(import.meta.url)))
const workspaceDir = path.dirname(frontendDir)
const backendDir = path.join(workspaceDir, 'backend')
const isWindows = process.platform === 'win32'
const pythonExe = path.join(backendDir, '.venv', 'Scripts', 'python.exe')
const pythonCommand = isWindows ? pythonExe : 'python3'

const backend = spawn(pythonCommand, ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000'], {
  cwd: backendDir,
  stdio: 'inherit',
  shell: false,
})

const frontendCommand = isWindows ? 'npm.cmd' : 'npm'
const frontend = spawn(frontendCommand, ['run', 'dev:frontend'], {
  cwd: frontendDir,
  stdio: 'inherit',
  shell: isWindows,
})

let stopping = false
function stop() {
  if (stopping) return
  stopping = true
  backend.kill('SIGTERM')
  frontend.kill('SIGTERM')
}

process.on('SIGINT', stop)
process.on('SIGTERM', stop)
backend.on('exit', (code) => {
  if (!stopping) {
    frontend.kill('SIGTERM')
    process.exitCode = code ?? 1
  }
})
frontend.on('exit', (code) => {
  if (!stopping) {
    backend.kill('SIGTERM')
    process.exitCode = code ?? 1
  }
})
