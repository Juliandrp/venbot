"""
Pasarelas de pago abstractas.

Soporta Stripe (global) y MercadoPago (LATAM).
Selección por settings.payment_provider.

Flujo típico:
  1. Tenant elige plan → POST /tenant/checkout/{plan_id}
     → genera URL de checkout y redirige
  2. Tenant paga en pasarela
  3. Pasarela llama webhook → POST /webhooks/payments/{provider}
     → activa el plan del tenant

Como Stripe y MercadoPago tienen SDKs distintos, exponemos dos clases con
la misma interfaz: crear_checkout() y verificar_webhook().
"""
import hmac
import hashlib
import json
from abc import ABC, abstractmethod
from app.config import settings


class PaymentProvider(ABC):
    @abstractmethod
    async def crear_checkout(
        self,
        plan_id: int,
        plan_nombre: str,
        precio_usd: float,
        tenant_id: str,
        success_url: str,
        cancel_url: str,
    ) -> str:
        """Retorna la URL de checkout a la que redirigir al tenant."""
        ...

    @abstractmethod
    def verificar_y_parsear_webhook(self, payload: bytes, headers: dict) -> dict | None:
        """
        Valida la firma del webhook y retorna:
          {"tenant_id": "...", "plan_id": 1, "evento": "completed"}
        o None si no es un evento de pago exitoso.
        """
        ...


class StripeProvider(PaymentProvider):
    def __init__(self):
        import stripe
        self.stripe = stripe
        stripe.api_key = settings.stripe_secret_key
        self.webhook_secret = settings.stripe_webhook_secret

    async def crear_checkout(
        self, plan_id, plan_nombre, precio_usd, tenant_id, success_url, cancel_url
    ) -> str:
        session = self.stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": f"Venbot — Plan {plan_nombre}"},
                    "unit_amount": int(precio_usd * 100),
                    "recurring": {"interval": "month"},
                },
                "quantity": 1,
            }],
            success_url=success_url,
            cancel_url=cancel_url,
            client_reference_id=tenant_id,
            metadata={"tenant_id": tenant_id, "plan_id": str(plan_id)},
        )
        return session.url

    def verificar_y_parsear_webhook(self, payload: bytes, headers: dict) -> dict | None:
        sig_header = headers.get("stripe-signature") or headers.get("Stripe-Signature")
        if not sig_header or not self.webhook_secret:
            return None
        try:
            event = self.stripe.Webhook.construct_event(payload, sig_header, self.webhook_secret)
        except Exception:
            return None

        if event["type"] not in ("checkout.session.completed", "invoice.payment_succeeded"):
            return None

        obj = event["data"]["object"]
        meta = obj.get("metadata") or {}
        tenant_id = meta.get("tenant_id") or obj.get("client_reference_id")
        plan_id = meta.get("plan_id")
        if not tenant_id or not plan_id:
            return None

        return {"tenant_id": tenant_id, "plan_id": int(plan_id), "evento": "completed"}


class MercadoPagoProvider(PaymentProvider):
    def __init__(self):
        import mercadopago
        self.sdk = mercadopago.SDK(settings.mercadopago_access_token)
        self.webhook_secret = settings.mercadopago_webhook_secret

    async def crear_checkout(
        self, plan_id, plan_nombre, precio_usd, tenant_id, success_url, cancel_url
    ) -> str:
        # MercadoPago usa "preferences" para checkout one-shot
        preference = {
            "items": [{
                "title": f"Venbot — Plan {plan_nombre}",
                "quantity": 1,
                "currency_id": "USD",
                "unit_price": float(precio_usd),
            }],
            "external_reference": f"{tenant_id}|{plan_id}",
            "back_urls": {
                "success": success_url,
                "failure": cancel_url,
                "pending": cancel_url,
            },
            "auto_return": "approved",
            "metadata": {"tenant_id": tenant_id, "plan_id": str(plan_id)},
        }
        result = self.sdk.preference().create(preference)
        return result["response"]["init_point"]

    def verificar_y_parsear_webhook(self, payload: bytes, headers: dict) -> dict | None:
        # MercadoPago firma con HMAC-SHA256 (header x-signature)
        firma = headers.get("x-signature") or headers.get("X-Signature")
        if firma and self.webhook_secret:
            esperado = hmac.new(
                self.webhook_secret.encode(),
                payload,
                hashlib.sha256,
            ).hexdigest()
            if esperado not in firma:
                return None

        try:
            data = json.loads(payload.decode())
        except Exception:
            return None

        # Notificaciones de tipo "payment" — consultar el pago para confirmar status=approved
        if data.get("type") != "payment":
            return None

        payment_id = data.get("data", {}).get("id")
        if not payment_id:
            return None

        try:
            pago = self.sdk.payment().get(payment_id)["response"]
        except Exception:
            return None

        if pago.get("status") != "approved":
            return None

        external_ref = pago.get("external_reference", "")
        if "|" not in external_ref:
            return None
        tenant_id, plan_id = external_ref.split("|", 1)
        return {"tenant_id": tenant_id, "plan_id": int(plan_id), "evento": "completed"}


def obtener_provider() -> PaymentProvider | None:
    """Retorna el provider configurado, o None si no hay pagos habilitados."""
    p = (settings.payment_provider or "").lower()
    if p == "stripe" and settings.stripe_secret_key:
        return StripeProvider()
    if p == "mercadopago" and settings.mercadopago_access_token:
        return MercadoPagoProvider()
    return None
