import { execSync } from 'child_process';
import path from 'path';
import { fileURLToPath } from 'url';

// Reemplazo para __dirname en ES Modules
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

async function globalSetup() {
  console.log('--- Reiniciando Base de Datos para Tests ---');
  try {
    // La ruta ahora es relativa a la carpeta del proyecto
    const scriptPath = path.resolve(__dirname, '../../../backend/scripts/reset_test_db_local.sh');
    console.log('Ejecutando script en:', scriptPath);
    
    execSync(`bash "${scriptPath}"`, { stdio: 'inherit' });
    console.log('--- Base de Datos Reiniciada con Éxito ---');
  } catch (error: any) {
    console.error('--- ERROR CRITICO en Global Setup ---');
    console.error(error.message);
    throw error;
  }
}

export default globalSetup;
