// Reexporta la función de web/functions para que Cloudflare Pages también la detecte
// si el proyecto se configura con la raíz del repositorio como directorio raíz.
export { onRequestGet } from '../web/functions/tidal.js';
