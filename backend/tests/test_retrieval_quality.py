"""How well retrieval actually answers the questions customers ask."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

# A small shop's help pages. Ordinary support writing, not keyword bait.
ARTICLES = [
    ("Returns and refunds", "Policies",
     "You can return anything within 30 days of delivery for a full refund. Items need to "
     "be unworn and in their original packaging with tags still attached. Start a return "
     "from your account, print the prepaid label and drop the parcel at any post office. "
     "Refunds go back to the original payment method within five working days of the "
     "parcel reaching us. Sale items can be returned for store credit rather than a refund."),
    ("Delivery times and shipping costs", "Policies",
     "Standard delivery takes three to five working days and is free on orders over fifty "
     "pounds. Express delivery arrives the next working day if you order before two in the "
     "afternoon. We ship across the United Kingdom and Europe. European orders take five to "
     "eight working days. You get a tracking link by email the moment your parcel leaves "
     "our warehouse."),
    ("Changing or cancelling an order", "Orders",
     "You can change or cancel an order any time before it ships. Open the order in your "
     "account and choose cancel, and the charge is released the same day. Once a parcel has "
     "left the warehouse we cannot stop it, so the quickest route is to refuse delivery."),
    ("Payment methods we accept", "Orders",
     "We take Visa, Mastercard, American Express, Apple Pay, Google Pay and PayPal. Payment "
     "is taken when the order ships, not when you place it, so a pending charge on your "
     "card is only a hold. We do not store card numbers, our payment provider does."),
    ("Warranty and faulty items", "Policies",
     "Everything we sell carries a two year warranty against manufacturing faults. Send a "
     "photo of the fault and your order number and we will replace or repair the item free "
     "of charge. Wear from normal use is not a manufacturing fault."),
    ("Track my order", "Orders",
     "Your tracking number arrives by email when the parcel ships. Paste it into the "
     "courier site to see where the parcel is. If tracking has not moved for three working "
     "days the parcel is probably stuck, so contact us and we will chase the courier."),
    ("Sizing and fit", "Products",
     "Every product page has a size chart with chest, waist and length measurements in "
     "centimetres. Our jackets run slightly large, so size down if you are between sizes. "
     "If the fit is wrong the return is free."),
    ("Discount codes and student pricing", "Orders",
     "Enter a discount code in the basket before checkout. One code per order, and codes do "
     "not stack with sale prices. Students get ten percent off once verified. Codes are "
     "case sensitive."),
]

# What people type, and the article that should answer it.
QUESTIONS = [
    ("How long do I have to return something", "Returns and refunds"),
    ("Can I get a refund on a jacket I never used", "Returns and refunds"),
    ("What is your returns policy", "Returns and refunds"),
    ("How long does delivery take", "Delivery times and shipping costs"),
    ("Is shipping free", "Delivery times and shipping costs"),
    ("Do you ship to europe", "Delivery times and shipping costs"),
    ("Can I cancel my order", "Changing or cancelling an order"),
    ("Do you take PayPal", "Payment methods we accept"),
    ("when will my card be charged", "Payment methods we accept"),
    ("my product broke is it under warranty", "Warranty and faulty items"),
    ("where is my parcel", "Track my order"),
    ("how do i track my order", "Track my order"),
    ("what size should I get", "Sizing and fit"),
    ("do you do student discount", "Discount codes and student pricing"),
]

# Nothing in the knowledge base covers these, so they belong to a person.
OFF_TOPIC = [
    "Can you help me refinance the mortgage on my houseboat",
    "What is the capital of France",
    "Who won the football last night",
]

MIN_TOP_ONE = 13
MIN_TOP_THREE = 14


async def _publish(client: AsyncClient, workspace: dict) -> None:
    for title, category, body in ARTICLES:
        created = await client.post(
            "/api/v1/knowledge",
            headers=workspace["headers"],
            json={
                "title": title, "category": category, "body": body,
                "status": "published", "visibility": "public",
            },
        )
        assert created.status_code == 201, created.text


@pytest.mark.asyncio
async def test_search_puts_the_right_article_first(
    client: AsyncClient, workspace: dict
) -> None:
    """The article that answers the question is the one ranked first."""
    await _publish(client, workspace)

    first = third = 0
    wrong = []
    for question, expected in QUESTIONS:
        found = await client.get(
            "/api/v1/knowledge/search",
            headers=workspace["headers"],
            params={"q": question, "limit": 3},
        )
        assert found.status_code == 200, found.text
        ranked = [hit["title"] for hit in found.json()]
        if ranked[:1] == [expected]:
            first += 1
        else:
            wrong.append(f"{question!r} wanted {expected!r} got {ranked[:1]}")
        if expected in ranked:
            third += 1

    assert first >= MIN_TOP_ONE, f"top one fell to {first}/{len(QUESTIONS)}\n" + "\n".join(wrong)
    assert third >= MIN_TOP_THREE, f"top three fell to {third}/{len(QUESTIONS)}"


@pytest.mark.asyncio
async def test_every_covered_question_is_answered_without_a_model(
    client: AsyncClient, workspace: dict
) -> None:
    """A customer asking something the articles cover gets an answer, not a queue."""
    await _publish(client, workspace)
    key = workspace["workspace"]["publicKey"]

    unanswered = []
    for question, _ in QUESTIONS:
        sent = await client.post(f"/api/v1/widget/{key}/messages", json={"body": question})
        assert sent.status_code == 200, sent.text
        reply = sent.json()["reply"]
        if reply is None:
            unanswered.append(question)
            continue
        # Invariant three. Nothing ungrounded reaches a customer.
        assert reply["meta"]["citations"], f"{question!r} was answered with no source"

    assert not unanswered, f"handed to a person despite being covered, {unanswered}"


@pytest.mark.asyncio
async def test_a_question_nothing_covers_goes_to_a_person(
    client: AsyncClient, workspace: dict
) -> None:
    """The other half of the promise. It says so rather than making it up."""
    await _publish(client, workspace)
    key = workspace["workspace"]["publicKey"]

    for question in OFF_TOPIC:
        sent = await client.post(f"/api/v1/widget/{key}/messages", json={"body": question})
        assert sent.status_code == 200, sent.text
        body = sent.json()
        assert body["reply"] is None, f"{question!r} got an answer, {body['reply']}"
        assert body["escalated"] is True, f"{question!r} was not handed to a person"


DEMO_QUESTIONS = [
    ("How long do I have to send a jacket back", "Returns and exchanges"),
    ("Can I return something I have not used", "Returns and exchanges"),
    ("What is your refund policy", "Returns and exchanges"),
    ("How much does delivery cost", "Shipping times and costs"),
    ("How fast is shipping", "Shipping times and costs"),
    ("Do you deliver to the highlands", "Shipping times and costs"),
    ("My parcel has not turned up", "Where is my order"),
    ("How do I track my delivery", "Where is my order"),
    ("Is my tent under warranty", "Gear warranty"),
    ("What size boots should I get", "Boot and pack sizing"),
    ("I found it cheaper elsewhere", "Price matching"),
    ("My order arrived smashed", "Item arrived damaged"),
    ("When will this be back in stock", "Backorders and restocks"),
    ("How do I wash my waterproof jacket", "Caring for technical fabrics"),
]


@pytest.mark.asyncio
async def test_the_demo_workspace_answers_its_own_customers(client: AsyncClient) -> None:
    """Every question above is answered from the article that covers it."""
    from app.db import async_session_maker
    from app.seed import load_fixture, seed

    async with async_session_maker() as db:
        workspace = await seed(db, load_fixture())
        await db.commit()
        key = workspace.public_key

    wrong = []
    for question, expected in DEMO_QUESTIONS:
        sent = await client.post(f"/api/v1/widget/{key}/messages", json={"body": question})
        assert sent.status_code == 200, sent.text
        reply = sent.json()["reply"]
        if reply is None:
            wrong.append(f"{question!r} was handed to a person")
            continue
        # The answer names the article it came from on its first line.
        named = reply["body"].splitlines()[0]
        if expected not in named:
            wrong.append(f"{question!r} wanted {expected!r} got {named!r}")

    assert not wrong, "the demo answers the wrong article\n" + "\n".join(wrong)
