from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ManagementMember(BaseModel):
    name: str
    title: str
    background: str | None = None


class DealExtraction(BaseModel):
    company_name: str | None = None
    company_description: str | None = None
    founded_year: int | None = None
    headquarters: str | None = None
    sector: str | None = None
    sub_sector: str | None = None
    business_model: str | None = None
    revenue_current: str | None = None
    revenue_prior_year: str | None = None
    revenue_growth_rate: str | None = None
    ebitda_current: str | None = None
    ebitda_margin: str | None = None
    arr: str | None = None
    gross_margin: str | None = None
    customer_count: int | None = None
    nrr: str | None = None
    asking_price_or_valuation: str | None = None
    deal_type: Literal[
        "buyout", "growth_equity", "venture", "credit", "real_estate"
    ] | None = None
    management_team: list[ManagementMember] = Field(default_factory=list)
    key_customers: list[str] = Field(default_factory=list)
    key_risks_mentioned: list[str] = Field(default_factory=list)
    competitive_advantages: list[str] = Field(default_factory=list)
    total_addressable_market: str | None = None
    geographic_markets: list[str] = Field(default_factory=list)
    employee_count: int | None = None
    other_notable_facts: list[str] = Field(default_factory=list)


class SearchResult(BaseModel):
    query: str
    url: str
    title: str
    content: str


class DealEnrichment(BaseModel):
    comparable_multiples: str | None = None
    recent_transactions: str | None = None
    company_news: str | None = None
    competitive_landscape: str | None = None
    sector_macro: str | None = None
    management_backgrounds: str | None = None
    sources: list[SearchResult] = Field(default_factory=list)


class MemoSection(BaseModel):
    section_id: str
    content: str
    word_count: int


class Memo(BaseModel):
    sections: dict[str, MemoSection]
    generated_at: datetime
    model_used: str
    total_tokens_used: int
