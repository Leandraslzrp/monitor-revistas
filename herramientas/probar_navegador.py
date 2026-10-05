"""Prueba si un navegador real (Chromium) puede leer las guías de grandes editoriales."""
import asyncio
from playwright.async_api import async_playwright

URLS = [
    "https://www.sciencedirect.com/journal/business-horizons/publish/guide-for-authors",
    "https://onlinelibrary.wiley.com/page/journal/14680262/homepage/forauthors.html",
    "https://www.tandfonline.com/action/authorSubmission?show=instructions&journalCode=recg20",
    "https://link.springer.com/journal/10734/submission-guidelines",
    "https://journals.sagepub.com/author-instructions/JMR",
    "https://academic.oup.com/restud/pages/General_Instructions",
    "https://www.emerald.com/insight/publication/issn/0048-3486",
]


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                              "(KHTML, like Gecko) Chrome/140.0 Safari/537.36"), locale="es-CL")
        for u in URLS:
            pg = await ctx.new_page()
            try:
                r = await pg.goto(u, timeout=45000, wait_until="domcontentloaded")
                await pg.wait_for_timeout(6000)
                t = await pg.inner_text("body")
                print("OK" if len(t) > 3000 else "CORTO", r.status if r else None, len(t), u)
                print("   ", " ".join(t.split())[:200])
            except Exception as ex:
                print("ERROR", u, str(ex)[:120])
            await pg.close()
        await b.close()

asyncio.run(main())
