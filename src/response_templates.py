"""
Template di risposte pre-strutturate per Gio.ia-bot.
L'AI può usare questi template riempiendoli con dati reali dal database.
"""
from typing import Optional, Dict, Any


def format_inventory_list(wines: list, limit: int = 50) -> str:
    """
    Formatta elenco inventario con quantità e prezzi.
    Usato quando l'utente chiede 'che vini ho?', 'lista inventario', ecc.
    """
    if not wines:
        return (
            "📋 **Inventario vuoto**\n"
            "━" * 30 + "\n"
            "Non ho trovato vini nel tuo inventario.\n\n"
            "💡 Puoi caricare un CSV o una foto con `/upload`"
        )
    
    wines_sorted = sorted(wines[:limit], key=lambda w: (w.name or "").lower())
    lines = ["📋 **Il tuo inventario**", "━" * 30]
    
    for idx, wine in enumerate(wines_sorted, start=1):
        name = wine.name or "Senza nome"
        producer = f" ({wine.producer})" if wine.producer else ""
        vintage = f" {wine.vintage}" if wine.vintage else ""
        
        qty = f"{wine.quantity} bott." if wine.quantity is not None else "n/d"
        price = f" - €{wine.selling_price:.2f}" if wine.selling_price else ""
        
        lines.append(f"{idx}. {name}{producer}{vintage} — {qty}{price}")
    
    if len(wines) > limit:
        lines.append(f"\n… e altri {len(wines) - limit} vini")
    
    lines.append("━" * 30)
    return "\n".join(lines)


def format_wine_quantity(wine: Any) -> str:
    """
    Template per risposta 'quanti X ho?'
    Es: 'quanti Barolo ho?' → '🍷 **Barolo Cannubi**\n📦 In cantina hai: 24 bottiglie'
    """
    name = wine.name or "Vino senza nome"
    producer = f" ({wine.producer})" if wine.producer else ""
    
    if wine.quantity is not None:
        return (
            f"🍷 **{name}{producer}**\n"
            f"{'━' * 30}\n"
            f"📦 **In cantina hai:** {wine.quantity} bottiglie\n"
            f"{'━' * 30}"
        )
    else:
        return (
            f"🍷 **{name}{producer}**\n"
            f"{'━' * 30}\n"
            f"❓ **Quantità non disponibile**\n"
            f"💡 Se vuoi, posso aggiungerla all'inventario!\n"
            f"{'━' * 30}"
        )


def format_wine_price(wine: Any) -> str:
    """
    Template per risposta 'a quanto vendo X?', 'prezzo di X?'
    Es: 'a quanto vendo Barolo?' → mostra prezzo vendita, acquisto, margine
    """
    name = wine.name or "Vino senza nome"
    producer = f" ({wine.producer})" if wine.producer else ""
    
    lines = [f"🍷 **{name}{producer}**", "━" * 30]
    
    if wine.selling_price:
        lines.append(f"💰 **Prezzo vendita:** €{wine.selling_price:.2f}")
    else:
        lines.append("❓ **Prezzo vendita non disponibile**")
    
    if wine.cost_price:
        lines.append(f"💵 **Prezzo acquisto:** €{wine.cost_price:.2f}")
        if wine.selling_price:
            margin = wine.selling_price - wine.cost_price
            margin_pct = (margin / wine.cost_price) * 100 if wine.cost_price > 0 else 0
            lines.append(f"📊 **Margine:** €{margin:.2f} ({margin_pct:.1f}%)")
    
    lines.append("━" * 30)
    return "\n".join(lines)


def format_wine_info(wine: Any) -> str:
    """
    Template per risposta 'dimmi tutto su X', 'informazioni su X', 'dettagli X'
    Mostra tutte le info disponibili sul vino
    """
    name = wine.name or "Vino senza nome"
    producer = f" ({wine.producer})" if wine.producer else ""
    
    lines = [f"🍷 **{name}{producer}**", "━" * 30]
    
    if wine.producer:
        lines.append(f"🏭 **Produttore:** {wine.producer}")
    
    if wine.region:
        location = wine.region
        if wine.country:
            location += f", {wine.country}"
        lines.append(f"📍 **Regione:** {location}")
    elif wine.country:
        lines.append(f"🇮🇹 **Paese:** {wine.country}")
    
    if wine.vintage:
        lines.append(f"📅 **Annata:** {wine.vintage}")
    
    if wine.grape_variety:
        lines.append(f"🍇 **Vitigno:** {wine.grape_variety}")
    
    if wine.quantity is not None:
        lines.append(f"📦 **Quantità:** {wine.quantity} bottiglie")
    
    if wine.wine_type:
        type_emoji = {
            "rosso": "🔴",
            "bianco": "⚪",
            "rosato": "🩷",
            "spumante": "🍾"
        }.get(wine.wine_type.lower(), "🍷")
        lines.append(f"{type_emoji} **Tipo:** {wine.wine_type.capitalize()}")
    
    if wine.classification:
        lines.append(f"⭐ **Classificazione:** {wine.classification}")
    
    if wine.selling_price:
        lines.append(f"💰 **Prezzo vendita:** €{wine.selling_price:.2f}")
    
    if wine.cost_price:
        lines.append(f"💵 **Prezzo acquisto:** €{wine.cost_price:.2f}")
    
    if wine.alcohol_content:
        lines.append(f"🍾 **Gradazione:** {wine.alcohol_content}% vol")
    
    if wine.description:
        lines.append(f"📝 **Descrizione:** {wine.description}")
    
    if wine.notes:
        lines.append(f"💬 **Note:** {wine.notes}")
    
    lines.append("━" * 30)

    # Calcola campi mancanti per consentire inserimento rapido via bot
    missing_fields = []
    if not wine.producer:
        missing_fields.append("producer")
    if not wine.region and not wine.country:
        # opzionale, non chiediamo sempre regione/paese
        pass
    if not wine.vintage:
        missing_fields.append("vintage")
    if not getattr(wine, 'grape_variety', None):
        missing_fields.append("grape_variety")
    if not getattr(wine, 'classification', None):
        missing_fields.append("classification")
    if getattr(wine, 'selling_price', None) is None:
        missing_fields.append("selling_price")
    if getattr(wine, 'cost_price', None) is None:
        missing_fields.append("cost_price")
    if getattr(wine, 'alcohol_content', None) is None:
        missing_fields.append("alcohol_content")
    if not getattr(wine, 'description', None):
        missing_fields.append("description")
    if not getattr(wine, 'notes', None):
        missing_fields.append("notes")

    text = "\n".join(lines)
    if missing_fields and getattr(wine, 'id', None) is not None:
        # Aggiungi marker nascosto per il bot: [[FILL_FIELDS:wine_id:field1,field2,...]]
        text += f"\n\n[[FILL_FIELDS:{wine.id}:{','.join(missing_fields)}]]"
    return text


def format_wine_not_found(wine_search_term: str) -> str:
    """
    Template quando un vino non è trovato nel database
    """
    return (
        f"❌ **Vino non trovato**\n"
        f"{'━' * 30}\n"
        f"Non ho trovato '{wine_search_term}' nel tuo inventario.\n\n"
        f"💡 **Cosa puoi fare:**\n"
        f"• Controlla l'ortografia del nome\n"
        f"• Usa `/inventario` per vedere tutti i vini\n"
        f"• Usa `/aggiungi` per aggiungere un nuovo vino\n"
        f"{'━' * 30}"
    )


def format_wine_exists(wine: Any) -> str:
    """
    Template per conferma presenza vino: 'X c'è?', 'hai X?', 'ce l'ho X?'
    """
    name = wine.name or "Vino senza nome"
    producer = f" ({wine.producer})" if wine.producer else ""
    qty_info = f" con {wine.quantity} bottiglie" if wine.quantity is not None else ""
    
    return (
        f"✅ **Sì, ce l'hai!**\n"
        f"{'━' * 30}\n"
        f"🍷 **{name}{producer}**{qty_info}\n"
        f"{'━' * 30}"
    )


def format_low_stock_alert(wines: list) -> str:
    """
    Template per avviso scorte basse
    """
    if not wines:
        return None
    
    lines = [
        "⚠️ **Scorte basse**",
        "━" * 30
    ]
    
    for wine in wines:
        name = wine.name or "Senza nome"
        qty = wine.quantity if wine.quantity is not None else 0
        min_qty = wine.min_quantity if wine.min_quantity is not None else 0
        lines.append(f"📦 {name} — {qty} bottiglie (min: {min_qty})")
    
    lines.append("━" * 30)
    lines.append("💡 Considera di riordinare questi vini!")
    
    return "\n".join(lines)


def format_inventory_summary(telegram_id: int, total_wines: int, total_quantity: int, low_stock_count: int) -> str:
    """
    Template per riepilogo inventario generale
    """
    return (
        f"📊 **Riepilogo inventario**\n"
        f"{'━' * 30}\n"
        f"🍷 **Totale vini:** {total_wines}\n"
        f"📦 **Totale bottiglie:** {total_quantity}\n"
        f"⚠️ **Scorte basse:** {low_stock_count} vini\n"
        f"{'━' * 30}"
    )


def format_movement_confirmation(wine_name: str, movement_type: str, quantity: int, 
                                   quantity_before: int, quantity_after: int) -> str:
    """
    Template per conferma movimento (consumo/rifornimento)
    """
    if movement_type == 'consumo':
        emoji = "📉"
        action = "Consumate"
    else:
        emoji = "📈"
        action = "Aggiunte"
    
    return (
        f"✅ **{movement_type.capitalize()} registrato**\n"
        f"{'━' * 30}\n"
        f"🍷 **Vino:** {wine_name}\n"
        f"📦 **Quantità:** {quantity_before} → {quantity_after} bottiglie\n"
        f"{emoji} **{action}:** {quantity} bottiglie\n"
        f"{'━' * 30}\n"
        f"💾 **Movimento salvato** nel sistema"
    )


# Dizionario per accesso rapido dell'AI
TEMPLATES = {
    "inventory_list": format_inventory_list,
    "wine_quantity": format_wine_quantity,
    "wine_price": format_wine_price,
    "wine_info": format_wine_info,
    "wine_not_found": format_wine_not_found,
    "wine_exists": format_wine_exists,
    "low_stock_alert": format_low_stock_alert,
    "inventory_summary": format_inventory_summary,
    "movement_confirmation": format_movement_confirmation,
}

