from django import template


register = template.Library()


@register.filter
def can(user, capability):
    return user.has_capability(capability)


@register.filter
def status_style(status):
    return {
        "DRAFT": "bg-slate-100 text-slate-700",
        "PREPARED": "bg-amber-100 text-amber-800",
        "DISPATCHED": "bg-blue-100 text-blue-800",
        "RECEIVING": "bg-cyan-100 text-cyan-800",
        "RECEIVED": "bg-emerald-100 text-emerald-800",
        "RECEIVED_DIFFERENCES": "bg-rose-100 text-rose-800",
        "CLOSED": "bg-indigo-100 text-indigo-800",
        "CANCELLED": "bg-slate-200 text-slate-500",
    }.get(status, "bg-slate-100 text-slate-700")


@register.filter
def status_daisy(status):
    return {
        "DRAFT": "badge-neutral badge-outline",
        "PREPARED": "badge-warning badge-outline",
        "DISPATCHED": "badge-info badge-outline",
        "RECEIVING": "badge-info badge-outline",
        "RECEIVED": "badge-success badge-outline",
        "RECEIVED_DIFFERENCES": "badge-error badge-outline",
        "CLOSED": "badge-neutral badge-outline",
        "CANCELLED": "badge-neutral badge-outline",
    }.get(status, "badge-neutral badge-outline")
