# Tumbleweed

Tumbleweed is a text and phone helper that connects people in food deserts to nearby food, assistance programs and community events. It needs no app, no browser and no fast internet. A basic phone that can send a text or make a call is enough.

## What it does

Text it something like *"I need food near 99344, no car"* or *"¿Dónde hay comida mañana?"* and it replies in a few seconds with:

- **Nearby food:** food banks, grocery stores and farmers markets, closest first, with addresses, hours and phone numbers.
- **Upcoming events:** free food distributions, community meals and market days.
- **Help with programs:** short, plain explanations of SNAP (food stamps), WIC and free school meals, with a link to the official page to apply.
- **Simple recipes** using only the ingredients someone already has.

It answers in the language you write in (English, Spanish, Tagalog or Vietnamese), and replies are kept to one short text. People who prefer to talk can call the same service and hear the same information spoken aloud.

## How it stays trustworthy

**The database decides what's true. The AI decides what to look up and how to say it.**

Every place, address, time and phone number comes from our own database. The AI never makes one up. If nothing is found nearby, it says so and points people to 2-1-1 for local help.

## How it works

1. Someone texts or calls the Tumbleweed number.
2. **Photon** (texts) or **ElevenLabs** (voice calls) passes the message to our server.
3. Our server, written in **Python** with **FastAPI**, asks **Claude** (Anthropic's AI) to understand the request.
4. Claude searches our **MongoDB Atlas** database of places and events by distance and opening day.
5. Claude writes a short, friendly reply, and our server sends it back as a text or as speech.

The server runs on **Railway**, a cloud hosting service.

## The stack

| Piece | What we use it for |
| --- | --- |
| Python + FastAPI | The server that receives messages and sends replies |
| Claude (Anthropic) | Understanding requests and writing replies in the user's language |
| MongoDB Atlas | Storing food places, events, and the ZIP code locations used to measure distance |
| Photon | Sending and receiving text messages and iMessages |
| ElevenLabs | Handling phone calls with a natural-sounding voice |
| Railway | Hosting the server online |

## Running it locally

The backend lives in `backend/`. You'll need [uv](https://docs.astral.sh/uv/) installed. Copy `backend/.env.example` to `backend/.env` and fill in your keys, then:

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload   # start the server
uv run ruff check . && uv run pytest -q  # lint and test
```

The demo data covers Othello (ZIP 99344) and Curlew (ZIP 99118) in Washington State. Some of the events are made up for the demo.
