"""Canonical shipment facts.

One Shipment is the truth for one bundle. Every document renders from it, so
a discrepancy between two documents can only exist because it was injected
deliberately — which is what makes the reconciliation label set exact.

Money is Decimal throughout. Floats would make invoice totals disagree with
their own line items by fractions of a cent, producing discrepancies nobody
injected.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class Party:
    name: str
    street: str
    city: str
    country: str

    @property
    def address_lines(self) -> list[str]:
        return [self.street, self.city, self.country]


@dataclass(frozen=True)
class Port:
    code: str
    name: str
    country: str

    def __str__(self) -> str:
        return f"{self.name}, {self.country} ({self.code})"


@dataclass(frozen=True)
class LineItem:
    description: str
    hts: str
    quantity: int
    unit: str
    unit_price: Decimal
    net_weight_kg: Decimal
    cartons: int
    tare_per_carton_kg: Decimal
    carton_cm: tuple[int, int, int]
    marks: str

    @property
    def amount(self) -> Decimal:
        return (self.unit_price * self.quantity).quantize(Decimal("0.01"))

    @property
    def gross_weight_kg(self) -> Decimal:
        """Net plus packaging. The bill of lading carries gross, the invoice net."""
        return (self.net_weight_kg + self.tare_per_carton_kg * self.cartons).quantize(
            Decimal("0.001")
        )

    @property
    def volume_cbm(self) -> Decimal:
        length, width, height = self.carton_cm
        per_carton = Decimal(length * width * height) / Decimal(1_000_000)
        return (per_carton * self.cartons).quantize(Decimal("0.001"))

    @property
    def dimensions(self) -> str:
        return "{} x {} x {} cm".format(*self.carton_cm)


@dataclass(frozen=True)
class Shipment:
    reference: str
    invoice_no: str
    invoice_date: date
    bl_no: str
    bl_date: date
    seller: Party
    buyer: Party
    notify_party: Party
    port_of_loading: Port
    port_of_discharge: Port
    vessel: str
    voyage: str
    incoterms: str
    currency: str
    freight: Decimal
    insurance: Decimal
    freight_terms: str
    containers: list[str] = field(default_factory=list)
    items: list[LineItem] = field(default_factory=list)

    @property
    def subtotal(self) -> Decimal:
        return sum((i.amount for i in self.items), Decimal("0.00"))

    @property
    def total(self) -> Decimal:
        return (self.subtotal + self.freight + self.insurance).quantize(Decimal("0.01"))

    @property
    def total_net_weight(self) -> Decimal:
        return sum((i.net_weight_kg for i in self.items), Decimal("0.000"))

    @property
    def total_cartons(self) -> int:
        return sum(i.cartons for i in self.items)

    @property
    def total_gross_weight(self) -> Decimal:
        return sum((i.gross_weight_kg for i in self.items), Decimal("0.000"))

    @property
    def total_volume_cbm(self) -> Decimal:
        return sum((i.volume_cbm for i in self.items), Decimal("0.000"))
