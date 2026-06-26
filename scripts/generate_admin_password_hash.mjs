import { createHash, randomBytes } from 'node:crypto';

const password = process.argv.slice(2).join(' ');
if (!password) {
  console.error('Použitie: node scripts/generate_admin_password_hash.mjs "silne admin heslo"');
  process.exit(1);
}

const salt = randomBytes(16);
const hash = createHash('sha256')
  .update(salt)
  .update(':')
  .update(password)
  .digest();

const encode = (buffer) => buffer.toString('base64url');
console.log(`sha256$${encode(salt)}$${encode(hash)}`);
