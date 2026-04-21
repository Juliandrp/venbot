"""Servicio de email via SMTP (configurable por tenant)."""
import aiosmtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from app.core.security import decrypt_secret


class EmailService:
    def __init__(self, config):
        self.host = config.smtp_host or ""
        self.port = config.smtp_port or 587
        self.user = config.smtp_user or ""
        self.password = decrypt_secret(config.smtp_password_enc) if config.smtp_password_enc else ""
        self.from_email = config.smtp_from_email or ""
        self.from_name = config.smtp_from_name or "Venbot"
        self.use_tls = config.smtp_use_tls

    async def enviar(self, destinatario: str, asunto: str, cuerpo_html: str) -> bool:
        """Envía un email HTML. Retorna True si fue exitoso."""
        if not all([self.host, self.user, self.from_email]):
            return False

        msg = MIMEMultipart("alternative")
        msg["Subject"] = asunto
        msg["From"] = f"{self.from_name} <{self.from_email}>"
        msg["To"] = destinatario
        msg.attach(MIMEText(cuerpo_html, "html", "utf-8"))

        try:
            await aiosmtplib.send(
                msg,
                hostname=self.host,
                port=self.port,
                username=self.user,
                password=self.password,
                use_tls=self.use_tls,
            )
            return True
        except Exception:
            return False

    async def enviar_confirmacion_pedido(self, destinatario: str, nombre: str, numero_pedido: str) -> bool:
        asunto = f"✅ Pedido confirmado #{numero_pedido}"
        cuerpo = f"""
        <h2>¡Hola {nombre}!</h2>
        <p>Tu pedido <strong>#{numero_pedido}</strong> ha sido confirmado y está siendo procesado.</p>
        <p>Te notificaremos cuando sea despachado.</p>
        <p>Gracias por tu compra.</p>
        """
        return await self.enviar(destinatario, asunto, cuerpo)

    async def enviar_estado_envio(
        self, destinatario: str, nombre: str, estado: str, numero_seguimiento: str | None
    ) -> bool:
        estados_texto = {
            "enviado": "¡Tu pedido fue despachado! 📦",
            "en_camino": "Tu pedido está en camino 🚚",
            "entregado": "¡Tu pedido fue entregado! 🎉",
            "fallido": "Tuvimos un problema con la entrega 😟",
        }
        asunto = estados_texto.get(estado, f"Actualización de tu pedido: {estado}")
        tracking_info = f"<p>Número de seguimiento: <strong>{numero_seguimiento}</strong></p>" if numero_seguimiento else ""
        cuerpo = f"""
        <h2>Hola {nombre},</h2>
        <p>{asunto}</p>
        {tracking_info}
        <p>Gracias por comprar con nosotros.</p>
        """
        return await self.enviar(destinatario, asunto, cuerpo)
