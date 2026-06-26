import { pbkdf2Sync, randomBytes } from 'node:crypto';

const password = process.argv.slice(2).join(' ');
if (!password) {
  console.error('Použitie: node scripts/generate_admin_password_hash.mjs "silne admin heslo"');
  process.exit(1);
}

const iterations = 310000;
const salt = randomBytes(16);
const hash = pbkdf2Sync(password, salt, iterations, 32, 'sha256');

const encode = (buffer) => buffer.toString('base64url');
console.log(`pbkdf2-sha256$${iterations}$${encode(salt)}$${encode(hash)}`);
