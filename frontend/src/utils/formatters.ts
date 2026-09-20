/**
 * Utilities for currency, percentage, and localized date formatting.
 */

/**
 * Format an ISO timestamp to Peruvian Local Time (America/Lima).
 * Expected format: "Datos calculados al DD/MM/AAAA HH:mm — hora de Perú"
 * Returns "Fecha de cálculo no disponible" if date is null, undefined or invalid.
 */
export function formatAnalyticsAsOf(asOf?: string | null): string {
  if (!asOf || typeof asOf !== "string" || !asOf.trim()) {
    return "Fecha de cálculo no disponible";
  }

  const d = new Date(asOf);
  if (isNaN(d.getTime())) {
    return "Fecha de cálculo no disponible";
  }

  try {
    const formatter = new Intl.DateTimeFormat("es-PE", {
      timeZone: "America/Lima",
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });

    const formattedParts = formatter.formatToParts(d);
    const partMap: Record<string, string> = {};
    for (const p of formattedParts) {
      partMap[p.type] = p.value;
    }

    const day = partMap.day || "00";
    const month = partMap.month || "00";
    const year = partMap.year || "0000";
    const hour = partMap.hour || "00";
    const minute = partMap.minute || "00";

    return `Datos calculados al ${day}/${month}/${year} ${hour}:${minute} — hora de Perú`;
  } catch {
    return "Fecha de cálculo no disponible";
  }
}

/**
 * Format monetary amount in PEN with thousands separator and S/ symbol.
 */
export function formatCurrencyPEN(amount?: string | number | null): string {
  if (amount === null || amount === undefined || amount === "") {
    return "S/ --";
  }
  const numericVal = typeof amount === "string" ? parseFloat(amount) : amount;
  if (isNaN(numericVal)) {
    return "S/ --";
  }

  return `S/ ${numericVal.toLocaleString("es-PE", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

/**
 * Format percentage with 2 decimals and % suffix.
 */
export function formatPercentage(pct?: string | number | null): string {
  if (pct === null || pct === undefined || pct === "") {
    return "0.00%";
  }
  const numericVal = typeof pct === "string" ? parseFloat(pct) : pct;
  if (isNaN(numericVal)) {
    return "0.00%";
  }

  return `${numericVal.toFixed(2)}%`;
}
