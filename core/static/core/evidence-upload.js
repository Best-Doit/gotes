/* Progressive enhancement: server validation remains authoritative. */
(() => {
  "use strict";
  const PHOTO_TARGET = 750 * 1024;
  const MAX_CAMERA_FILE = 30 * 1024 * 1024;
  const uncertain = "No se pudo confirmar si la evidencia se guardó. Revisa las evidencias del traspaso antes de volver a enviarla.";

  function loadPhoto(file) {
    return new Promise((resolve, reject) => {
      const url = URL.createObjectURL(file);
      const picture = new Image();
      const timer = setTimeout(() => finish(new Error("El celular tardó demasiado en abrir la foto. Prueba con una imagen de menor resolución.")), 15000);
      function finish(error) {
        clearTimeout(timer);
        picture.onload = picture.onerror = null;
        URL.revokeObjectURL(url);
        if (error) { picture.src = ""; reject(error); }
        else resolve(picture);
      }
      picture.onload = () => finish();
      picture.onerror = () => finish(new Error("No se pudo abrir la foto. Selecciona una imagen JPG, PNG o WEBP válida."));
      picture.src = url;
    });
  }

  function encode(canvas, quality) {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("No se pudo preparar la foto a tiempo. Selecciona una imagen más pequeña.")), 15000);
      canvas.toBlob(blob => {
        clearTimeout(timer);
        if (blob) resolve(blob);
        else reject(new Error("El celular no pudo preparar la foto. Prueba con una imagen de menor resolución."));
      }, "image/jpeg", quality);
    });
  }

  async function prepare(file, maxBytes) {
    if (/\.(heic|heif)$/i.test(file.name) || /^image\/hei[cf]/i.test(file.type)) {
      throw new Error("Esta foto está en HEIC/HEIF. Exporta o toma la foto en JPG (modo compatible) y vuelve a seleccionarla.");
    }
    if (!/\.(jpe?g|png|webp|pdf)$/i.test(file.name)) {
      throw new Error("Formato no permitido. Selecciona una foto JPG, PNG, WEBP o un PDF.");
    }
    if (!file.size) throw new Error("La foto está vacía. Vuelve a tomarla o seleccionarla.");
    const isPhoto = /\.(jpe?g|png|webp)$/i.test(file.name);
    const target = Math.min(PHOTO_TARGET, maxBytes);
    if (isPhoto && file.size > target) {
      if (file.size > MAX_CAMERA_FILE) throw new Error("La foto supera 30 MB. Tómala con menor resolución para poder prepararla en el celular.");
      const picture = await loadPhoto(file);
      const canvas = document.createElement("canvas");
      try {
        const scale = Math.min(1, 1920 / Math.max(picture.naturalWidth, picture.naturalHeight));
        const width = Math.max(1, Math.round(picture.naturalWidth * scale));
        const height = Math.max(1, Math.round(picture.naturalHeight * scale));
        for (const [size, quality] of [[1, 0.86], [1, 0.72], [0.8, 0.7]]) {
          canvas.width = Math.round(width * size);
          canvas.height = Math.round(height * size);
          const context = canvas.getContext("2d");
          if (!context) throw new Error("El navegador no puede preparar esta foto. Prueba con una imagen más pequeña.");
          context.fillStyle = "#ffffff";
          context.fillRect(0, 0, canvas.width, canvas.height);
          context.drawImage(picture, 0, 0, canvas.width, canvas.height);
          const blob = await encode(canvas, quality);
          if (blob.size <= target) return { blob, name: file.name.replace(/\.[^.]+$/, ".jpg") };
        }
        throw new Error("No se pudo reducir la foto al tamaño permitido. Selecciona una imagen de menor resolución.");
      } finally {
        canvas.width = canvas.height = 1;
        picture.src = "";
      }
    }
    if (file.size > maxBytes) throw new Error(`El archivo supera el límite de ${maxBytes / 1024 / 1024} MB.`);
    return { blob: file, name: file.name };
  }

  function upload(form, data, onProgress) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.upload.onprogress = event => onProgress(event.lengthComputable ? Math.round(event.loaded * 100 / event.total) : null);
      xhr.open("POST", form.action);
      xhr.setRequestHeader("Accept", "application/json");
      xhr.timeout = 60000;
      xhr.onerror = () => reject(new Error("Se perdió la conexión. " + uncertain));
      xhr.ontimeout = () => reject(new Error("La conexión o el servidor tardaron demasiado. " + uncertain));
      xhr.onabort = () => reject(new Error("Se interrumpió la subida. " + uncertain));
      xhr.onload = () => {
        let result;
        try { result = JSON.parse(xhr.responseText); } catch (_) { result = null; }
        if (xhr.status >= 200 && xhr.status < 300 && result?.ok && result.redirect_url) {
          const destination = new URL(result.redirect_url, window.location.href);
          if (destination.origin === window.location.origin) { resolve(destination.href); return; }
        }
        let message = result?.error;
        if (!message && xhr.status === 413) message = "El servidor rechazó el tamaño del archivo. Usa una foto más pequeña o pide revisar el límite de subida del servidor.";
        if (!message && (xhr.status === 403 || xhr.responseURL.includes("/login/"))) message = "Tu sesión expiró o no tienes permiso. Vuelve a iniciar sesión y revisa el traspaso.";
        reject(new Error(message || "El servidor no confirmó la carga. " + uncertain));
      };
      xhr.send(data);
    });
  }

  document.querySelectorAll("form[data-evidence-upload]").forEach(form => {
    const input = form.querySelector('input[type="file"]');
    if (!input || !window.FormData || !window.XMLHttpRequest || !HTMLCanvasElement.prototype.toBlob) return;
    const status = document.createElement("div");
    status.className = "mt-2 text-sm sm:col-span-2";
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    status.hidden = true;
    const text = document.createElement("p");
    const progress = document.createElement("progress");
    progress.className = "progress w-full";
    progress.max = 100;
    progress.value = 0;
    progress.setAttribute("aria-label", "Progreso de subida de evidencia");
    status.append(text, progress);
    form.append(status);
    let busy = false;
    form.addEventListener("submit", async event => {
      event.preventDefault();
      if (busy || !form.reportValidity()) return;
      const file = input.files[0];
      if (!file) return;
      busy = true;
      // form.elements includes the submit button outside the reception form.
      const buttons = Array.from(form.elements).filter(element => element.type === "submit");
      const states = buttons.map(button => button.disabled);
      buttons.forEach(button => { button.disabled = true; });
      form.setAttribute("aria-busy", "true");
      status.hidden = false;
      status.classList.remove("text-error");
      progress.hidden = false;
      progress.value = 0;
      text.textContent = "Preparando foto o archivo…";
      try {
        const data = new FormData(form);
        const prepared = await prepare(file, Number(input.dataset.maxBytes) || 5 * 1024 * 1024);
        data.set(input.name, prepared.blob, prepared.name);
        text.textContent = "Subiendo evidencia…";
        const target = await upload(form, data, percent => {
          progress.value = percent || 0;
          text.textContent = percent === 100 ? "Archivo enviado. Esperando confirmación del servidor…" : `Subiendo evidencia${percent === null ? "…" : `: ${percent}%`}`;
        });
        text.textContent = "Evidencia guardada. Abriendo el traspaso…";
        window.location.assign(target);
      } catch (error) {
        text.textContent = error.message;
        status.classList.add("text-error");
        progress.hidden = true;
        status.scrollIntoView({ block: "nearest" });
      } finally {
        busy = false;
        form.removeAttribute("aria-busy");
        buttons.forEach((button, index) => { button.disabled = states[index]; });
      }
    });
  });
})();
