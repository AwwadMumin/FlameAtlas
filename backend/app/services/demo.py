"""Ready-made /api/assess requests for the demo. Numbers come from the mission presets (knowledge pack), not from code."""
from __future__ import annotations

from app.models.api import AssessRequest, DemoScenario, DemoScenariosResponse
from app.services.assess import PSI_TO_KPA, _presets


def scenarios() -> DemoScenariosResponse:
    P = _presets()

    def at(pid: str) -> dict:
        p = P[pid]
        return {"preset_id": pid, "oxygen_pct": p["o2_pct"], "pressure_kpa": round(p["pressure_psia"] * PSI_TO_KPA, 2)}

    return DemoScenariosResponse(scenarios=[
        DemoScenario(id="pmma_iss", title="ISS cabin — PMMA (acrylic)", description="What does NASA microgravity data say about acrylic at ISS cabin air?",
                     request=AssessRequest(material_query="acrylic", gravity="orbit", question="will it self-extinguish?", **at("iss"))),
        DemoScenario(id="sibal_iss", title="ISS cabin — SIBAL fabric", description="Cotton-fiberglass fabric at ISS cabin air: evidence, 1g baseline and flags.",
                     request=AssessRequest(material_query="SIBAL", gravity="orbit", **at("iss"))),
        DemoScenario(id="pet_exploration", title="Lunar habitat 34% O2 — PET", description="PET at the exploration atmosphere on the Moon: outside the data domain, nearest evidence only.",
                     request=AssessRequest(material_query="PET", gravity="moon", **at("exploration"))),
        DemoScenario(id="unknown_mars", title="Unknown material — Mars", description="A material not in the data, char yield 30%: Van Krevelen 1g estimate, no microgravity verdict.",
                     request=AssessRequest(material_query="Zorbium-7", gravity="mars", unknown_material_props={"char_yield_pct": 30, "polymer_family": "polyester"}, **at("exploration")))])
