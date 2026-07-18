# -*- coding: utf-8 -*-
"""Static-site generator for hpma.org. Emits plain HTML files (no runtime dep)."""
import os, glob, html, json

# Repo root = parent of this _tools/ folder, so the script is portable.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Canonical domain. Baked into canonical URLs, Open Graph tags and sitemap.xml;
# takes full effect when hpma.org DNS points at this site.
SITE = "https://hpma.org"
WRITTEN = []  # canonical URLs of every generated page, for sitemap.xml

def canonical(path):
    return SITE + "/" + (path[:-len("index.html")] if path.endswith("index.html") else path)

NAV = """  <ul class="nav-menu">
    <li class="has-sub"><a href="{p}about/">About</a>
      <ul class="submenu">
        <li><a href="{p}about/">About the Pointe</a></li>
        <li><a href="{p}about/our-place.html">Our Place</a></li>
        <li><a href="{p}about/history.html">Our Stories &amp; History</a></li>
      </ul>
    </li>
    <li class="has-sub"><a href="{p}governance/">Governance</a>
      <ul class="submenu">
        <li><a href="{p}governance/">Governance</a></li>
        <li><a href="{p}governance/committees.html">Committees</a></li>
        <li><a href="{p}governance/documents.html">Governing Documents</a></li>
      </ul>
    </li>
    <li class="has-sub"><a href="{p}amenities/">Amenities</a>
      <ul class="submenu">
        <li><a href="{p}amenities/">All Amenities</a></li>
        <li><a href="{p}amenities/clubhouse.html">Clubhouse</a></li>
        <li><a href="{p}amenities/pool-spa.html">Pool &amp; Spa</a></li>
        <li><a href="{p}amenities/marina.html">Marina</a></li>
        <li><a href="{p}amenities/boat-rv-storage.html">Boat &amp; RV Storage</a></li>
        <li><a href="{p}amenities/fitness-center.html">Fitness Center</a></li>
        <li><a href="{p}amenities/outdoor-recreation.html">Outdoor Recreation</a></li>
        <li><a href="{p}amenities/picnic-shelters.html">Picnic Shelters</a></li>
        <li><a href="{p}amenities/trails.html">Trails</a></li>
        <li><a href="{p}amenities/pea-patch.html">Pea Patch</a></li>
        <li><a href="{p}amenities/wildlife.html">Wildlife</a></li>
      </ul>
    </li>
    <li class="has-sub"><a href="{p}community/">Community</a>
      <ul class="submenu">
        <li><a href="{p}community/">Community</a></li>
        <li><a href="{p}community/exploring-the-area.html">Exploring the Area</a></li>
        <li><a href="{p}community/considering-the-pointe.html">Considering the Pointe</a></li>
      </ul>
    </li>
    <li><a href="{p}visiting/">Visiting</a></li>
    <li><a href="{p}photos/">Photos</a></li>
    <li class="nav-search"><button class="search-toggle" aria-label="Search this site"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-4.1-4.1"/></svg><span class="label">Search</span></button></li>
    <li><a href="https://app.condocontrol.com/login" class="portal" target="_blank" rel="noopener">Owner Portal</a></li>
  </ul>"""

HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} &middot; Hartstene Pointe</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{url}">
<meta property="og:site_name" content="Hartstene Pointe">
<meta property="og:type" content="website">
<meta property="og:title" content="{title} &middot; Hartstene Pointe">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{site}/{herobg}">
<meta name="twitter:card" content="summary_large_image">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<link rel="icon" type="image/png" href="{p}assets/img/logo.png">
<link rel="apple-touch-icon" href="{p}assets/img/logo.png">
<link rel="stylesheet" href="{p}assets/css/site.css">
</head>
<body>
<a class="skip" href="#main">Skip to content</a>

<div class="util">
  <span class="left">Harstine Island &middot; South Puget Sound, Washington</span>
  <span class="right">
    <a href="{p}contact/">Contact</a>
    <a href="https://www.hpwsd.org/" target="_blank" rel="noopener">Water &amp; Sewer District &#8599;</a>
    <a href="https://app.condocontrol.com/login" target="_blank" rel="noopener">Owner Portal &#8599;</a>
  </span>
</div>

<nav class="nav">
  <a class="brand" href="{p}index.html" aria-label="Hartstene Pointe Maintenance Association home">
    <img class="brand-mark" src="{p}assets/img/logo.png" alt="Hartstene Pointe crest" width="42" height="42">
    <span class="wm">HARTSTENE POINTE</span>
  </a>
  <button class="search-toggle" aria-label="Search this site"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-4.1-4.1"/></svg><span class="label">Search</span></button>
  <button class="nav-toggle" aria-label="Menu" aria-expanded="false"><span></span><span></span><span></span></button>
{nav}
</nav>

<main id="main" data-pagefind-body>
  <header class="page-hero">
    <div class="bg" style="background-image:url('{p}{herobg}')"></div>
    <div class="wrap">
      <nav class="crumbs" data-pagefind-ignore>{crumbs}</nav>
      <h1>{h1}</h1>
      {lede}
    </div>
  </header>
"""

FOOT = """</main>

<footer class="foot">
  <div class="wrap">
    <div class="cols">
      <div>
        <img class="foot-mark" src="{p}assets/img/logo-light.png" alt="Hartstene Pointe crest" width="38" height="38">
        <div class="wm">HARTSTENE POINTE</div>
        <div class="sub">Maintenance Association</div>
        <p>202 E Pointes Dr. East<br>Shelton, WA 98584<br><a href="tel:+13604262300">(360) 426-2300</a><br><a href="mailto:office@hpma.org">office@hpma.org</a></p>
      </div>
      <div><h4>Explore</h4><ul>
        <li><a href="{p}amenities/">Amenities</a></li>
        <li><a href="{p}visiting/">Visiting the Pointe</a></li>
        <li><a href="{p}community/exploring-the-area.html">Exploring the Area</a></li>
        <li><a href="{p}amenities/marina.html">Marina</a></li>
        <li><a href="{p}photos/">Photos</a></li>
      </ul></div>
      <div><h4>Association</h4><ul>
        <li><a href="{p}about/">About</a></li>
        <li><a href="{p}governance/">Governance</a></li>
        <li><a href="{p}governance/documents.html">Governing Documents</a></li>
        <li><a href="{p}community/considering-the-pointe.html">Considering the Pointe</a></li>
        <li><a href="{p}contact/">Contact</a></li>
      </ul></div>
      <div class="hours"><h4>Office Hours</h4>
        <p><b>Mon&ndash;Fri</b><br>8:30am&ndash;5:00pm</p>
        <p><b>Saturday</b><br>10:00am&ndash;Noon</p>
        <p><a href="https://app.condocontrol.com/login" target="_blank" rel="noopener">Owner Portal &#8599;</a></p>
      </div>
    </div>
    <div class="base">
      <span>&copy; 2026 Hartstene Pointe Maintenance Association.</span>
      <span>Harstine Island, South Puget Sound, Washington</span>
    </div>
  </div>
</footer>

<script src="{p}assets/js/site.js"></script>
</body>
</html>
"""

def page(path, title, h1, crumbs, body, herobg="assets/img/hero-marina.jpg", lede="", desc=""):
    depth = path.count("/")
    p = "../" * depth
    lede_html = f"<p>{lede}</p>" if lede else ""
    crumb_html = ' <span style="opacity:.5">/</span> '.join(crumbs)
    # unescape-then-escape so pre-entitied strings ("&amp;") don't double-escape
    esc = lambda s: html.escape(html.unescape(s))
    out = HEAD.format(title=esc(title), desc=esc(desc or lede or h1), p=p,
                      nav=NAV.format(p=p), herobg=herobg, crumbs=crumb_html,
                      h1=h1, lede=lede_html, url=canonical(path), site=SITE)
    out += "\n" + body + "\n"
    out += FOOT.format(p=p)
    full = os.path.join(ROOT, path.replace("/", os.sep))
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(out)
    WRITTEN.append(canonical(path))
    print("wrote", path)

def home_link(depth=1):
    return f'<a href="{"../"*depth}index.html">Home</a>'

# ------------------------------------------------------------------ PAGES

# ============ ABOUT ============
page("about/index.html", "About the Pointe", "About the Pointe",
     [home_link(), "About"],
     herobg="assets/img/pages/olympics-firs.jpg",
     desc="Hartstene Pointe is a private gated community of 532 homesites on 215 wooded acres at the north tip of Harstine Island in Mason County, WA, established 1970, with 3.5 miles of private beach and a 110-slip marina.",
     lede="A unique community on the northern tip of Harstine Island, set within a verdant forest and surrounded on three sides by the waters of Puget Sound.",
     body="""  <section class="article"><div class="wrap"><div class="split">
    <div class="prose">
      <p>Hartstene Pointe is a unique community located on the northern tip of Harstine Island, set within a verdant forest, and surrounded on three sides by the waters of Puget Sound. The Pointe is approximately 215 acres in size and is situated about 18 miles northeast of the City of Shelton in Mason County, Washington.</p>
      <figure><img src="../assets/img/amenities/entrance-sign.jpg" alt="The Hartstene Pointe entrance sign"><figcaption>The entrance to Hartstene Pointe.</figcaption></figure>
      <p>In 1970 Weyerhaeuser established Hartstene Pointe as a not-for-profit corporation. While Hartstene Pointe was originally planned to be a recreational community, a significant number of the homes serve as primary residences today. The Pointe consists of 532 private residential lots, 90 of which are condominium &ldquo;Island Houses&rdquo;, along with a private road system, a 6,000&nbsp;sq.&nbsp;ft. Clubhouse, a swimming pool and hot tub, three tennis courts, a basketball court, a pickleball court, about 5.5 miles of walking trails, a 110-slip marina, a boat launch, picnic areas and 3.5 miles of private beach.</p>
      <p>Decades on, Hartstene Pointe remains heavily wooded with Douglas fir, hemlock, cedar, madrona, maple and various other deciduous trees. The area is also home to a significant population of birds, deer and raccoons, and bald eagles have been sighted along the water's edge. Along its perimeter, Hartstene Pointe gives magnificent views of Puget Sound, Mt. Rainier and the Olympic Mountains.</p>

      <h2>HPMA, the organization</h2>
      <p>&ldquo;The Pointe&rdquo; is incorporated as a non-profit homeowners' association, as described in our <a href="../governance/">Governance</a> section. HPMA is governed by a seven-member Board of Directors and administered by a General Manager, with a staff of five full-time employees and up to eight part-time patrol, pool-monitor and maintenance personnel.</p>

      <h2>Harstine Island, a remote paradise</h2>
      <p>Harstine Island, approximately ten miles long and three miles wide, is located at the southern end of Puget Sound, 18 miles from the nearest town, Shelton. The island is accessible by a bridge from Highway 3 that links Shelton to Bremerton.</p>
      <p>Lured by the quiet beauty and low cost of land, early settlers farmed, logged, planted orchards, and gathered clams and oysters from the sea. The settlers built schools and stores, and in 1914 volunteers erected the Community Hall, which is still actively used today. Electricity and telephone were not available on the island until 1947. A ferry provided transportation across the passage until 1969, when a bridge was built connecting the island to the mainland. Hartstene Pointe development followed soon afterward.</p>

      <div class="callout"><h4>The Hartstene Pointe Water-Sewer District</h4><p>The community established the Hartstene Pointe Water-Sewer District, which acquired the water and sewer utilities formerly owned and operated by Mason County. The District is a totally separate government entity and is not run by Hartstene Pointe. Visit <a href="https://www.hpwsd.org/" target="_blank" rel="noopener">hpwsd.org</a> for service and billing.</p></div>
    </div>
    <aside class="aside">
      <h4>At a glance</h4>
      <div class="info-row"><b>Established</b><span>1970, by Weyerhaeuser</span></div>
      <div class="info-row"><b>Size</b><span>~215 acres</span></div>
      <div class="info-row"><b>Homes &amp; lots</b><span>532 lots (incl. 90 Island Houses)</span></div>
      <div class="info-row"><b>Waterfront</b><span>3.5 miles of private beach</span></div>
      <div class="info-row"><b>Marina</b><span>110 slips at Indian Cove</span></div>
      <div class="info-row"><b>Trails</b><span>~5.5 miles</span></div>
      <div class="info-row"><b>Governance</b><span>7-member Board of Directors</span></div>
      <div class="info-row"><b>Staff</b><span>5 full-time (incl. General Manager) &amp; up to 8 part-time</span></div>
      <div class="info-row"><b>Island population</b><span>1,412 (Harstine Island)</span></div>
      <div class="info-row"><b>Location</b><span>Harstine Island, Mason County, WA</span></div>
      <p style="margin-top:16px"><a class="btn ghost" href="our-place.html">Our Place &amp; maps</a></p>
    </aside>
  </div></div></section>""")

page("about/our-place.html", "Our Place", "Our Place",
     [home_link(), '<a href="index.html">About</a>', "Our Place"],
     lede="Where we are, how the island came to be, and what it's like to live at the Pointe.",
     body="""  <section class="article"><div class="wrap"><div class="prose">
    <h2>Harstine Island</h2>
    <p>Harstine Island, approximately ten miles long and three miles wide, is located at the southern end of Puget Sound, 18 miles away from the nearest town, Shelton. The island is accessible by a bridge from Highway 3 that links Shelton to Bremerton. The island's name has worn several spellings over the years, Harstine and Hartstene among them, and more than one story explains why.</p>
    <p>Lured by the quiet beauty and low cost of land, early settlers farmed, logged, planted orchards, and gathered clams and oysters from the sea. The settlers built schools and stores, and in 1914 volunteers erected the Community Hall, which is still actively used today. Electricity and telephone were not available on the island until 1947. A ferry provided transportation across the passage until 1969, when a bridge was built connecting the island to the mainland.</p>

    <h2>Hartstene Pointe</h2>
    <p>In 1970 Weyerhaeuser established Hartstene Pointe as a not-for-profit corporation. Located on the northern tip of the island, it is an unincorporated community of 532 home sites, surrounded by common green-belt property. While Hartstene Pointe was originally planned to be a recreational community, a significant share of the homes serve as primary residences today.</p>
    <p>The Pointe employs a full-time Manager, office, patrol and maintenance staff, and is governed by a seven-member Board of Directors elected by the property owners. The Board functions under the Covenants, Conditions and Restrictions (CC&amp;Rs). To protect the wooded character of the Pointe, all development, including new construction, additions, exterior maintenance and painting, and tree cutting, is reviewed by the Permit Review Committee.</p>
    <p>There is a 6,000-square-foot Clubhouse with a library, a swimming pool and spa, three tennis courts, a basketball court, a playground, a pickleball court, 5.5 miles of walking trails, a 110-slip marina, a boat launch, picnic areas and 3.5 miles of beach. The community remains heavily wooded with Douglas fir, hemlock, cedar, madrona and maple, and is home to deer, raccoons and many birds, with bald eagles sighted along the water's edge.</p>

    <h2>Where are we?</h2>
    <p>Hartstene Pointe is on the northern tip of Harstine Island in Mason County, Washington, reached by the Harstine Island bridge off Highway 3, about 18 miles from Shelton, the county seat. Detailed community maps are available on the <a href="../governance/documents.html">Governing Documents</a> page and at the HPMA office.</p>
    <figure><img src="../assets/img/pages/washington-map.png" alt="Map of Washington showing Harstine Island in South Puget Sound"><figcaption>Harstine Island sits in South Puget Sound, in Mason County, Washington.</figcaption></figure>

    <h2>On the water</h2>
    <p>The region's clear, deep waters offer world-class shrimp and salmon fishing, scuba diving, and miles of pristine shoreline for boaters, kayakers and beachcombers. Bald eagles, seals and shorebirds are part of daily life along the water's edge.</p>

    <h2>Exploring the area</h2>
    <p>There is a great deal to explore beyond the Pointe. Immediately west of Shelton are Olympic National Park and Olympic National Forest, with mountain trails, temperate rainforests, waterfalls and sweeping vistas. Closer to home, Harstine Island and Case Inlet hold several worthwhile destinations:</p>
    <ul>
      <li><strong>Jarrell Cove State Park</strong>, a quiet marine park on the north end of the island, popular with boaters and campers.</li>
      <li><strong>McMicken Island State Park</strong>, a boat-in marine state park just offshore.</li>
      <li><strong>Stretch Point State Park</strong>, a small boat-in park with one of the area's nicer swimming beaches.</li>
      <li><strong>Wild Felid Advocacy Center</strong>, a wild-cat sanctuary on the island that is home to roughly 60 cats.</li>
    </ul>
    <p>There is much more nearby, from Hood Canal shellfish houses to the trails of the Olympics. See our <a href="../community/exploring-the-area.html">Exploring the Area</a> guide for favorites.</p>

    <div class="callout"><h4>Island-ready, together</h4><p>Part of the charm of island life is its self-reliance, and neighbors here look out for one another. The Association's Disaster Preparedness volunteers help the community stay ready for winter weather and the occasional power outage. You can learn more on the <a href="../governance/committees.html">Committees</a> page.</p></div>
  </div></div></section>""")

page("about/history.html", "Our Stories &amp; History", "Our Stories &amp; History",
     [home_link(), '<a href="index.html">About</a>', "History"],
     lede="The people and memories behind the Pointe, gathered from residents past and present.",
     body="""  <section class="article"><div class="wrap"><div class="split">
    <div class="prose">
      <h2>Collective memories</h2>
      <p>Once upon a time, four would-be historians were struck by a sobering thought: most of the original residents from the 1970s had left, for one reason or another. As their numbers dwindled, so did the sources of the oral history of the beginnings of Hartstene Pointe.</p>
      <p>A plan was made to find them and listen to their stories. To support sometimes-contradictory accounts, some memories clear as a bell, others foggy in the details, they gleaned through the archives of board meetings, newsletters, correspondence, personal letters and lawsuits.</p>
      <figure><img src="../assets/img/history/harstine-island.jpg" alt="Historical view of Harstine Island"><figcaption>Harstine Island, the setting for the Pointe's story.</figcaption></figure>

      <h2>Stories from the Pointe</h2>
      <p>A collection of remembrances contributed by residents over the years:</p>
      <ul class="doclist">
        <li><a href="../assets/docs/history-looking-back-42-years.pdf" target="_blank" rel="noopener"><span class="doc-ic">PDF</span>Looking Back at 42 Years<span class="doc-note">Rick &amp; Peggy Johnson</span></a></li>
        <li><a href="../assets/docs/history-the-pointe-of-caring.pdf" target="_blank" rel="noopener"><span class="doc-ic">PDF</span>The Pointe of Caring<span class="doc-note">by Suzanne Bonciolini</span></a></li>
        <li><a href="../assets/docs/history-to-the-pointe.pdf" target="_blank" rel="noopener"><span class="doc-ic">PDF</span>To the Point(e): How We Came to Live at the Pointe<span class="doc-note">by Suzanne Bonciolini</span></a></li>
        <li><a href="../assets/docs/history-thad-and-liz-thomas.pdf" target="_blank" rel="noopener"><span class="doc-ic">PDF</span>Thad &amp; Liz Thomas's Tale<span class="doc-note">as reported by Fiona Leslie</span></a></li>
        <li><a href="../assets/docs/history-my-love-of-the-pointe.pdf" target="_blank" rel="noopener"><span class="doc-ic">PDF</span>My Love of the Pointe<span class="doc-note">Laura St. George</span></a></li>
      </ul>
      <p style="font-size:14px;color:var(--rock)">Additional remembrances, including Shirley Marrs' memories as an original pioneer, Ken Brown on the island forest, and Walt Tupper's &ldquo;Welcome to Fantasy Island&rdquo;, are held in the Association archives.</p>

      <h2>Before the Pointe: the island's story</h2>
      <p>Hartstene Pointe occupies the northern tip of a much older place. A welcome sign at the Harstine Island community hall, drawn from <em>The Island Remembers</em> and the state parks department, tells the island's longer history, and it is worth retelling here.</p>
      <p>The first caretakers of the island were the ancestors of the Squaxin Island Tribe, guided by the give and take between people and nature. They gathered shellfish, hunted game and harvested berries in ways that left the wild character of the island intact. Two trees were treasured above the rest: the Pacific yew, whose strong, flexible wood made bows and canoe paddles and whose bark and needles were brewed into healing teas (modern medicine later drew the cancer drug taxol from the same tree), and the great red cedar, whose soft inner bark was pounded into supple fabric for clothing, baskets and mats.</p>
      <p>In 1841 Commander Charles Wilkes, anchored off Fort Nisqually near the end of a four-year exploratory voyage, gave the island its name. His logbook recorded it as &ldquo;Harstein,&rdquo; and over the years at least five spellings competed before &ldquo;Harstine&rdquo; settled in as the island's own. The community that Weyerhaeuser laid out here in the 1970s took the older, softer spelling, Hartstene, which is why the two names differ to this day.</p>
      <p>Robert Jarrell became the first permanent European settler in 1872, homesteading 160 acres; in 1878 he married Philura, the first European woman on the island, and Jarrells Cove, now home to a marina and a state park, still carries their name. Logging followed and became the island's major industry, and the second- and third-growth Douglas fir, western red cedar, hemlock, madrona, maple and alder that shade the Pointe today grew up in its wake, home to the eagles, deer, raccoon, fox and coyote that residents still see.</p>
      <ul>
        <li>A two-story log cabin built by the Bustrack family in <strong>1888</strong> still stands, moved to high ground to keep it safe.</li>
        <li>The <strong>Island Belle</strong> grape, bred locally by Adam Eckert in <strong>1890</strong>, was well suited to Puget Sound and became a genuine agricultural success.</li>
        <li>The first telephone line linked two island farms in <strong>1911</strong>; a dependable line to the mainland was not established until <strong>1946</strong>.</li>
        <li>The community hall was raised by volunteer labor in <strong>1914</strong>, lit by gas lamps until electricity finally reached it in the late <strong>1940s</strong>.</li>
        <li>Ferry service began in <strong>1922</strong> with the <em>Island Belle</em>, a 40-foot scow driven by side paddle wheels that could carry three cars. It ran until the new bridge opened on <strong>June 22, 1969</strong>, connecting the island to the mainland for good.</li>
      </ul>
      <p>It was onto this quiet, wooded island, a few years after the bridge replaced the ferry, that Hartstene Pointe was drawn.</p>

      <h2>The original vision</h2>
      <p>Not long ago a resident turned up the original sales brochure that The Quadrant Corporation, a Weyerhaeuser company, used to introduce Hartstene Pointe when lots first went on the market in the mid-1970s. Its photographs and typewritten pages are a window into how the Pointe was imagined at the very beginning.</p>
      <blockquote>There's something about an island like Hartstene in Puget Sound that takes you &ldquo;out of this world&rdquo; the minute you cross the bridge from the mainland. It's a quieter, live-and-let-live world, developed by the people who care. Hartstene Pointe is one of those rare, nearby getaway places where the trees still outnumber the people, and always will.</blockquote>
      <figure><img src="../assets/img/history/island-house-sketch.jpg" alt="Pen-and-ink drawing of an Island House on its deck among the trees, from the 1970s brochure"><figcaption>An Island House, as drawn for the original brochure.</figcaption></figure>
      <p>The brochure describes a community where each lot &ldquo;adjoins a wooded, permanently deeded green belt,&rdquo; where &ldquo;even the lodge, tennis courts, and swimming pool are embraced by forest,&rdquo; and where about half the land belongs to everyone, including more than three miles of beach. Owners were invited to swim in the heated clubhouse pool, water ski in the calm waters of Pickering Passage, fish for sea run cutthroat, or walk the sandy beach and dig for butter clams.</p>
      <figure><img src="../assets/img/history/brochure-map-1975.jpg" alt="Illustrated 1975 plat map of Hartstene Pointe showing the island, its circular lots, the Recreation Center, Indian Cove, the lagoon and Case Inlet"><figcaption>The community as drawn for the brochure, dated May 1975. The Recreation Center, Island Houses, Indian Cove and the lagoon are already in place.</figcaption></figure>
      <p>A fact sheet tucked inside spelled out the particulars: roughly 215 acres, about half of it common greenbelt; circular lots 80 to 90 feet across, each separated by at least ten feet of green belt for privacy; paved blacktop roads and underground utilities; a 6,000-square-foot clubhouse with a full kitchen; three and a half miles of community beach; a heated pool, a wading pool and a Jacuzzi; and some five and a half miles of pedestrian trails &ldquo;with wooden bridges across draws and ravines.&rdquo; An architectural committee, it noted, would review and approve all building plans, the same role the Permit Review Committee fills today.</p>
      <div class="figrow two">
        <figure><img src="../assets/img/history/view-from-pointe-1970s.jpg" alt="1970s photograph looking out from Hartstene Pointe across the water to a wooded island"><figcaption>&ldquo;View from Pointe,&rdquo; from the brochure.</figcaption></figure>
        <figure><img src="../assets/img/history/picnic-area-1970s.jpg" alt="1970s photograph of one of the shoreline picnic areas at Hartstene Pointe"><figcaption>&ldquo;One of four picnic areas,&rdquo; in the 1970s.</figcaption></figure>
      </div>
      <p>Even the crest at the top of this site traces back to that first brochure: the green shield with its mountain, sun and water was the mark Quadrant chose for Hartstene Pointe, and it has watched over the community ever since.</p>

      <h2>Contribute a story</h2>
      <p>We invite contributions of stories to enhance our history. Send them to the office via our <a href="../contact/">contact page</a>.</p>
    </div>
    <aside class="aside">
      <h4>Did you know?</h4>
      <div class="info-row"><b>Water, 1972</b><span>$1/month for undeveloped lots, $2 for lots with homes</span></div>
      <div class="info-row"><b>Sewer</b><span>$1 per lot, $5 for a home</span></div>
      <div class="info-row"><b>Dues</b><span>$8 a month</span></div>
      <div class="info-row"><b>Taxes</b><span>1.13% of market value</span></div>
      <h4 style="margin-top:22px">Island House rental, 1970s</h4>
      <div class="info-row"><b>Summer week</b><span>$175</span></div>
      <div class="info-row"><b>Summer month</b><span>$375</span></div>
      <div class="info-row"><b>Winter month</b><span>$315</span></div>
      <div class="info-row"><b>A summer day</b><span>$40</span></div>
    </aside>
  </div></div></section>""")

# ============ GOVERNANCE ============
# One canonical, public-facing list of committees, shared by the Governance
# and Committees pages. It is a sampling of what the community offers, not a
# roster — both lists end with "and more" on purpose.
COMMITTEES = [
    "Permit Review",
    "Common Area Stewardship",
    "Disaster Preparedness",
    "Long Range Planning",
    "Fire Safety",
    "Pea Patch",
    "Island House",
    "Moorage",
    "Recreation",
]
COMMITTEE_LIS = "\n        ".join(f"<li>{c}</li>" for c in COMMITTEES) \
    + "\n        <li>&hellip; and more</li>"

page("governance/index.html", "Governance", "Governance",
     [home_link(), "Governance"],
     lede="How decisions are made at the Pointe, and how owners take part in making them.",
     body="""  <section class="article"><div class="wrap"><div class="split">
    <div class="prose">
      <p>Simply put, <em>governance</em> is how decisions get made at the Pointe, and how they get carried out. It takes in the people, formal and informal alike, who shape those decisions, and the structures the community has set up to see them through.</p>

      <h2>Our formal structure</h2>
      <p>Four documents, together, set the framework for life at the Pointe:</p>
      <ul>
        <li>Articles of Incorporation</li>
        <li>CC&amp;Rs (Covenants, Conditions &amp; Restrictions)</li>
        <li>Bylaws</li>
        <li>Rules &amp; Regulations</li>
      </ul>
      <p>You can read all of these on the <a href="documents.html">Governing Documents</a> page. The Board has also established several committees in the Bylaws; these committees advise the Board, though decisions remain the Board's to make.</p>

      <h2>How it works in practice</h2>
      <p>Property owners elect a seven-member Board of Directors each June; terms run three years, so two or three seats come up for election in any given year. The Board elects its own officers: President, Vice-President, Secretary and Treasurer.</p>
      <p>The Board meets twice a month, on the 2nd Thursday and the 3rd Saturday. These meetings are open to property owners only, and not to the general public, guests, or prospective buyers. The Saturday meeting is where business affecting all property owners is conducted, and owners are urged to attend and participate. While owners are encouraged to present their views, the Board has the final decision-making authority.</p>

      <h2>The informal system</h2>
      <p>In addition to the formal system, the Pointe has a number of informal, ad-hoc committees, task forces, groups and individuals who are self-organizing and take on various roles within the community. These neighbors carry much of the Pointe's ongoing work and activity, and their voices keep the Board informed on the issues that matter.</p>
    </div>
    <aside class="aside">
      <h4>Board committees</h4>
      <ul>
        {COMMITTEE_LIS}
      </ul>
      <p style="margin-top:14px"><a class="btn ghost" href="committees.html">About committees</a></p>
    </aside>
  </div></div></section>""".replace("{COMMITTEE_LIS}", COMMITTEE_LIS))

page("governance/committees.html", "Committees", "Committees",
     [home_link(), '<a href="index.html">Governance</a>', "Committees"],
     lede="Many owners volunteer to serve on committees that help the community in countless ways.",
     body="""  <section class="article"><div class="wrap"><div class="split">
    <div class="prose">
      <h2>The role of committees</h2>
      <p>Many people at the Pointe volunteer to serve on committees to help the community in various ways. Our Bylaws let the Board appoint advisory committees, often called Standing Committees, that serve for the long haul with ongoing responsibilities and charges from the Board.</p>
      <p>The Bylaws describe how each committee works, who serves on it, what it looks after, and how long it runs, so volunteers always know the shape of the job they are taking on.</p>

      <h2>Ad-hoc committees</h2>
      <p>Some committees are established by the Board for a limited time or purpose, and others simply emerge on their own. Examples have included a Roads Committee and a Bluff Erosion group, along with many groups that form for a certain purpose and then disband when it is achieved.</p>

      <div class="callout"><h4>A community of volunteers</h4><p>Every committee is staffed by owners who volunteer their time and expertise. For current owners, committee openings and ways to serve are posted in the <a href="https://app.condocontrol.com/login" target="_blank" rel="noopener">Owner Portal</a>.</p></div>
    </div>
    <aside class="aside">
      <h4>Board advisory committees</h4>
      <ul>
        {COMMITTEE_LIS}
      </ul>
      <h4 style="margin-top:20px">Ad-hoc examples</h4>
      <ul>
        <li>Roads Committee</li>
        <li>Bluff Erosion</li>
        <li>&hellip; and others that come &amp; go</li>
      </ul>
    </aside>
  </div></div></section>""".replace("{COMMITTEE_LIS}", COMMITTEE_LIS))

DOCS = """  <section class="article"><div class="wrap"><div class="prose">
    <p>The documents that govern Hartstene Pointe are provided below as PDFs. <strong>CC&amp;Rs differ between plats</strong>, please refer to the document that applies to your property.</p>

    <h2>Core documents</h2>
    <ul class="doclist">
      <li><a href="../assets/docs/bylaws.pdf" target="_blank" rel="noopener"><span class="doc-ic">PDF</span>Bylaws<span class="doc-note">Revised 10-19-2024</span></a></li>
      <li><a href="../assets/docs/rules-and-regulations.pdf" target="_blank" rel="noopener"><span class="doc-ic">PDF</span>Rules &amp; Regulations<span class="doc-note">Revised 10-19-2024</span></a></li>
    </ul>

    <h2>CC&amp;Rs by plat</h2>
    <ul class="doclist">
      <li><a href="../assets/docs/ccrs-circle-lots.pdf" target="_blank" rel="noopener"><span class="doc-ic">PDF</span>CC&amp;Rs, Circle Lots</a></li>
      <li><a href="../assets/docs/ccrs-rectangular-lots.pdf" target="_blank" rel="noopener"><span class="doc-ic">PDF</span>CC&amp;Rs, Rectangular Lots</a></li>
      <li><a href="../assets/docs/ccrs-island-house.pdf" target="_blank" rel="noopener"><span class="doc-ic">PDF</span>CC&amp;Rs, Island Houses</a></li>
    </ul>

    <h2>Moorage</h2>
    <ul class="doclist">
      <li><a href="../assets/docs/moorage-agreement.pdf" target="_blank" rel="noopener"><span class="doc-ic">PDF</span>Moorage Agreement &amp; Declaration, Indian Cove</a></li>
      <li><a href="../assets/docs/moorage-rules.pdf" target="_blank" rel="noopener"><span class="doc-ic">PDF</span>Moorage Rules &amp; Handbook<span class="doc-note">Current 5-21-2022</span></a></li>
    </ul>

    <h2>Maps</h2>
    <ul class="doclist">
      <li><a href="../assets/docs/trail-map.pdf" target="_blank" rel="noopener"><span class="doc-ic">PDF</span>Hartstene Pointe Trail Map</a></li>
    </ul>

    <div class="callout"><p>Looking for something not listed here? The <a href="../contact/">HPMA office</a> can help with Articles of Incorporation, additional plat CC&amp;Rs, and other records.</p></div>
  </div></div></section>"""
page("governance/documents.html", "Governing Documents", "Governing Documents",
     [home_link(), '<a href="index.html">Governance</a>', "Documents"],
     lede="Articles, CC&amp;Rs, Bylaws, Rules &amp; Regulations, moorage documents and maps.",
     body=DOCS)

# ============ AMENITIES INDEX ============
AM = [
 ("clubhouse.html","Clubhouse","assets/img/amenities/clubhouse.jpg","6,000 sq. ft. of gathering space, a library, and the entrance to the pool."),
 ("pool-spa.html","Pool &amp; Spa","assets/img/amenities/pool.jpg","A swimming pool and hot tub with seasonal hours, steps from the Clubhouse."),
 ("marina.html","Marina","assets/img/amenities/marina.jpg","Indian Cove Marina, 110 slips in a sheltered cove, with short-term moorage for owners and their guests."),
 ("boat-rv-storage.html","Boat &amp; RV Storage","assets/img/amenities/boat-rv-storage.jpg","On-site storage for boats, trailers, RVs, kayaks and canoes."),
 ("fitness-center.html","Fitness Center","assets/img/amenities/fitness.jpg","Open 24 hours with cardio machines, weights and more, gate card required."),
 ("outdoor-recreation.html","Outdoor Recreation","assets/img/amenities/recreation.jpg","Tennis, pickleball, basketball, playgrounds, horseshoes and fire pits."),
 ("picnic-shelters.html","Picnic Shelters","assets/img/amenities/picnic.jpg","Five picnic areas around the Pointe, from North Beach to the Spit."),
 ("trails.html","Trails","assets/img/amenities/trails.jpg","About 5.5 miles of marked trails through ravines and along the bluffs."),
 ("pea-patch.html","Pea Patch Garden","assets/img/amenities/pea-patch.jpg","A community garden started in 2006 by owners with a shared vision."),
 ("wildlife.html","Wildlife &amp; Habitat","assets/img/amenities/wildlife.jpg","The deer, eagles, shorebirds and wildflowers that make their home alongside us."),
]
cards = "".join(
 f'<a class="acard" href="{u}"><div class="ph" style="background-image:url(\'../{img}\')"></div>'
 f'<div class="bd"><h4>{t}</h4><p>{d}</p><span class="go">Explore &rarr;</span></div></a>\n'
 for (u,t,img,d) in AM)
page("amenities/index.html", "Amenities", "Amenities",
     [home_link(), "Amenities"],
     lede="The Pointe is fortunate to have a wide range of amenities for owners and their guests to enjoy, cared for by the General Manager and staff with advice from the Recreation, Moorage and Common Area Stewardship committees.",
     body=f'  <section class="article"><div class="wrap"><div class="grid-3">\n{cards}  </div></div></section>')

# ============ AMENITY SUB-PAGES ============
def amenity(u, title, h1, hero, lede, body, desc=""):
    page("amenities/"+u, title, h1,
         [home_link(), '<a href="index.html">Amenities</a>', h1.replace("&amp;","&")],
         lede=lede, herobg=hero, body=body, desc=desc)

amenity("clubhouse.html","Clubhouse","Clubhouse","assets/img/amenities/clubhouse.jpg",
 "The heart of the community, 6,000 square feet of gathering space overlooking the Pointe.",
 """  <section class="article"><div class="wrap"><div class="split">
    <div class="prose">
      <p>The Hartstene Pointe Clubhouse offers something for everyone in the community.</p>
      <figure><img src="../assets/img/pages/aerial-clubhouse.jpg" alt="Aerial view of the Clubhouse, pool and tennis courts"><figcaption>The Clubhouse, pool, spa and tennis courts, tucked into the forest.</figcaption></figure>
      <h3>Our Clubhouse offers</h3>
      <ul>
        <li>Manager and business office (for residents)</li>
        <li>Multi-purpose room, activities, meetings, ping pong, pool, chess and checkers</li>
        <li>Library, books, magazines, DVDs and puzzles</li>
        <li>Kitchen (for scheduled events)</li>
        <li>Bulletin boards and information posting</li>
        <li>An outside gazebo with fireplace, for meetings and events</li>
        <li>Entrance to the pool &amp; spa</li>
        <li>Comfortable easy chairs for relaxing</li>
        <li>Free Wi-Fi</li>
      </ul>
      <p style="font-size:14px;color:var(--rock)">Children 12 and under must be supervised by an adult.</p>
      <h2>The Library</h2>
      <p>The Library is full of great reads, ranging from children's books and non-fiction to magazines and classic novels. All books are donated and may be checked out by all Pointe residents and their guests on an honor system. There are also games, puzzles and DVD and VCR movies. A team of volunteers maintains the Library for the benefit of the community.</p>
      <figure><img src="../assets/img/pages/library.jpg" alt="The library inside the Hartstene Pointe Clubhouse"><figcaption>The community library, maintained by resident volunteers.</figcaption></figure>
    </div>
    <aside class="aside">
      <h4>Clubhouse hours</h4>
      <div class="hours-box">
        <div class="row"><span><b>Winter</b><br>Mon&ndash;Sun</span><span>8am&ndash;5pm</span></div>
        <div class="row"><span><b>Summer</b><br>Sun&ndash;Thu</span><span>8am&ndash;9pm</span></div>
        <div class="row"><span><b>Summer</b><br>Fri&ndash;Sat</span><span>8am&ndash;10pm</span></div>
      </div>
      <p style="margin-top:16px;font-size:13px;color:var(--rock)">Hours are seasonal; check posted notices for holiday changes.</p>
    </aside>
  </div></div></section>""")

amenity("pool-spa.html","Pool &amp; Spa","Pool &amp; Spa","assets/img/amenities/pool.jpg",
 "A swimming pool and hot tub, steps from the Clubhouse, no reservation required.",
 """  <section class="article"><div class="wrap"><div class="split">
    <div class="prose">
      <p>The pool and spa sit just behind the Clubhouse and are open to residents and their guests from around Memorial Day through Labor Day. Come in from the parking lot west of the Clubhouse, and sign in when you arrive.</p>
      <h3>Good to know</h3>
      <ul>
        <li>There is no lifeguard on duty; everyone swims at their own risk.</li>
        <li>Children 12 and under must be supervised by an adult.</li>
        <li>Quiet-swim and all-swim times are posted at the pool.</li>
        <li>Bring your own towels and your keycard for entry.</li>
        <li>Equipment for the courts can be checked out at the pool.</li>
        <li>No reservation needed, just come on down.</li>
      </ul>
      <figure><img src="../assets/img/pages/aerial-clubhouse.jpg" alt="Aerial view of the pool, spa and Clubhouse"><figcaption>The pool and spa sit just behind the Clubhouse, with the courts nearby.</figcaption></figure>
      <figure><img src="../assets/img/pages/community-pool.jpg" alt="A summer day at the Hartstene Pointe pool"><figcaption>A summer afternoon at the pool.</figcaption></figure>
      <figure><img src="../assets/img/pages/pool-spa.jpg" alt="The heated pool and spa ringed by fir trees behind the Clubhouse"><figcaption>The heated pool and spa, ringed by firs behind the Clubhouse.</figcaption></figure>
    </div>
    <aside class="aside">
      <h4>Summer pool hours</h4>
      <p style="font-size:12px;color:var(--rock);margin-bottom:10px">Memorial weekend &ndash; Labor Day weekend</p>
      <div class="info-row"><b>Quiet swim &middot; every day</b><span>9&ndash;10am &amp; 5&ndash;6pm</span></div>
      <div class="info-row"><b>All swim &middot; Sun&ndash;Thu</b><span>10am&ndash;5pm &amp; 6&ndash;9pm</span></div>
      <div class="info-row"><b>All swim &middot; Fri&ndash;Sat</b><span>10am&ndash;5pm &amp; 6&ndash;10pm</span></div>
    </aside>
  </div></div></section>""")

amenity("marina.html","Marina","Marina","assets/img/amenities/marina.jpg",
 "Indian Cove Marina, a 110-slip working marina tucked into a wooded cove.",
 body="""  <section class="article"><div class="wrap"><div class="split">
    <div class="prose">
      <h2>Indian Cove Marina</h2>
      <p>The marina is a treasured amenity of the Pointe, set in a sheltered cove on the community's west side.</p>
      <div class="figrow">
        <figure><img src="../assets/img/pages/marina-aerial.jpg" alt="Indian Cove Marina from above"><figcaption>Indian Cove Marina from above.</figcaption></figure>
        <figure><img src="../assets/img/pages/marina-twilight.jpg" alt="The marina at twilight"><figcaption>The docks at twilight.</figcaption></figure>
        <figure><img src="../assets/img/pages/marina-heron.jpg" alt="A great blue heron standing on the marina docks"><figcaption>A great blue heron patrols the docks.</figcaption></figure>
      </div>
      <h3>Guest and transient moorage</h3>
      <p>Indian Cove is a private, owner's marina, and there is no public or visitor moorage. Owners without a long-term slip, registered occupants, and guests accompanied by their host owner are welcome to arrange short-term moorage through the Harbormaster or the amenity booking service in the <a href="https://app.condocontrol.com/login" target="_blank" rel="noopener">Owner Portal</a>, which is also where the arrival details and current requirements are kept.</p>
      <h3>About the marina</h3>
      <ul>
        <li>More than 100 slips from 20 to 55 feet. Slips are leased long-term and may be held or transferred only by Hartstene Pointe lot owners, you must own a lot at the Pointe to hold a slip.</li>
        <li>Tucked into a sheltered cove, gated and watched over by security cameras.</li>
      </ul>
      <p>Kayak and canoe rack storage and the community's two boat launches are separate from Indian Cove Marina. Those are covered on the <a href="boat-rv-storage.html">Boat &amp; RV Storage</a> page.</p>
      <h2>A little history</h2>
      <p>When Quadrant developed Hartstene Pointe in the 1970s, many buyers believed they were promised a marina. A settlement led to a 20-slip marina. Years later, 100 property owners funded the current 110-slip marina themselves, a $400,000 investment in the community. Under the agreement with HPMA, the leaseholders keep the marina running at no cost to the wider Association: annual moorage assessments support its upkeep, insurance, the Harbormaster and the Washington State shoreline lease, with funds set aside for future dredging and major repairs.</p>
    </div>
    <aside class="aside">
      <h4>Harbormaster</h4>
      <div class="info-row"><b>Phone</b><span><a href="tel:+13602293137">(360) 229-3137</a></span></div>
      <div class="info-row"><b>Email</b><span><a href="mailto:harbormaster@hpma.org">harbormaster@hpma.org</a></span></div>
      <h4 style="margin-top:20px">Reference</h4>
      <ul>
        <li><a href="../assets/docs/moorage-rules.pdf" target="_blank" rel="noopener">Moorage Rules &amp; Handbook<span class="doc-tag">PDF</span></a></li>
        <li><a href="../assets/docs/moorage-agreement.pdf" target="_blank" rel="noopener">Moorage Agreement &amp; Declaration<span class="doc-tag">PDF</span></a></li>
      </ul>
      <p style="margin-top:14px"><a class="btn" href="https://app.condocontrol.com/login" target="_blank" rel="noopener">Owner Portal &#8599;</a></p>
    </aside>
  </div></div></section>""",
 desc="Indian Cove Marina at Hartstene Pointe: a private 110-slip marina on Harstine Island, WA. Slips are held by lot owners; short-term moorage for owners and guests via the Harbormaster.")

amenity("boat-rv-storage.html","Boat &amp; RV Storage","Boat &amp; RV Storage","assets/img/amenities/boat-rv-storage.jpg",
 "On-site storage for boats, trailers, RVs, kayaks and canoes, available to all owners.",
 """  <section class="article"><div class="wrap"><div class="prose">
    <p>The Pointe offers on-site storage for boats and trailers, RVs, utility trailers, kayaks and canoes, available to all owners. Kayak and canoe racks are found at the marina and other locations, and the community has two boat launches.</p>
    <h2>Lagoon Ramp</h2>
    <p>This ramp has a dock and is located in the lagoon at the east end, accessed by the road off Chesapeake that goes to the spit. It is only for smaller boats (under about 25 feet) and can only be used at high tide. When entering or exiting the lagoon, keep to the outside, there is a sand bar in the middle.</p>
    <h2>Case Inlet Ramp</h2>
    <p>This ramp has no dock and is accessed by the other road off Chesapeake.</p>
    <div class="callout"><p>Contact the <a href="../contact/">HPMA office</a> for current storage fees and availability.</p></div>
  </div></div></section>""")

amenity("fitness-center.html","Fitness Center","Fitness Center","assets/img/amenities/fitness.jpg",
 "Open 24 hours a day, across the road from the Clubhouse, gate card required for entry.",
 """  <section class="article"><div class="wrap"><div class="split">
    <div class="prose">
      <p>Enjoy our Fitness Center, located down a small road across the street from the Clubhouse, in the Maintenance Facility Building. Park at the Clubhouse and walk in. It is open 24 hours a day and a keycard is required for entry.</p>
      <h3>Good to know</h3>
      <ul>
        <li>The center is geared for adults; children 12 and under must be supervised by an adult.</li>
        <li>A quick wipe-down of the equipment before and after use keeps it fresh for the next neighbor (cleansers and sanitizers are provided).</li>
        <li>Sign in on the clipboard when you arrive.</li>
      </ul>
      <h3>Equipment</h3>
      <ul>
        <li>2 &times; Vision Fitness ellipticals</li>
        <li>Vision Fitness spinning bike, treadmill and recumbent bike</li>
        <li>Rowing machine</li>
        <li>Vectra 1800 single-stack universal weight machine</li>
        <li>Free-weight bench &amp; squat rack</li>
        <li>Weslo Cardio Glide</li>
        <li>Assorted dumbbells and exercise mats</li>
      </ul>
      <div class="figrow">
        <figure><img src="../assets/img/amenities/elliptical.jpg" alt="Elliptical trainers in the Fitness Center"><figcaption>Vision Fitness ellipticals</figcaption></figure>
        <figure><img src="../assets/img/amenities/fitness-vectra.jpg" alt="Vectra 1800 weight machine"><figcaption>Vectra 1800 weight machine</figcaption></figure>
        <figure><img src="../assets/img/amenities/hand-weights.jpg" alt="Free weights and dumbbells"><figcaption>Free weights and dumbbells</figcaption></figure>
      </div>
    </div>
    <aside class="aside">
      <h4>Equipment manuals</h4>
      <ul>
        <li><a href="../assets/docs/elliptical-trainer-manual.pdf" target="_blank" rel="noopener">Elliptical trainer manual<span class="doc-tag">PDF</span></a></li>
        <li><a href="../assets/docs/indoor-cycle-manual.pdf" target="_blank" rel="noopener">Indoor cycle manual<span class="doc-tag">PDF</span></a></li>
      </ul>
      <h4 style="margin-top:20px">Recreation Committee</h4>
      <p>Owner volunteers on the Recreation Committee advise the Association on the fitness center and other recreation amenities.</p>
    </aside>
  </div></div></section>""")

amenity("outdoor-recreation.html","Outdoor Recreation","Outdoor Recreation","assets/img/amenities/recreation.jpg",
 "Beyond the beaches, there are outdoor facilities for all ages to enjoy.",
 """  <section class="article"><div class="wrap"><div class="prose">
    <p>In addition to the beautiful beaches that surround the Pointe, there are outdoor recreational facilities for all ages to enjoy. Here is a snapshot of just a few:</p>
    <figure><img src="../assets/img/pages/aerial-clubhouse.jpg" alt="Aerial view of the tennis courts, pool and Clubhouse"><figcaption>The tennis and pickleball courts, pool and Clubhouse from above.</figcaption></figure>
    <ul>
      <li><strong>Tennis courts</strong>, two near the Clubhouse, one by the spit</li>
      <li><strong>Basketball &amp; pickleball court</strong>, near the Clubhouse</li>
      <li><strong>Fire pits</strong>, at the Spit</li>
      <li><strong>Playground equipment</strong>, North Beach and the Clubhouse area</li>
      <li><strong>Horseshoes</strong>, North Beach</li>
      <li><strong>Hiking</strong>, about 5.5 miles of community <a href="trails.html">trails</a>, plus 3.5 miles of private beach</li>
    </ul>
    <p style="font-size:14px;color:var(--rock)">Equipment for the tennis, pickleball and basketball courts can be checked out at the pool.</p>

    <h3>Play structure</h3>
    <p>A play structure for small children is located behind the Clubhouse gazebo, next to the pool. Children must be supervised by an adult.</p>

    <h3>Fire pits at the Spit</h3>
    <p>Fire pits and charcoal barbecues are available at the Spit, along with some chairs and picnic tables. Bring your own firewood, and be sure it fits inside the fire rings. Extinguish all fires when you leave, using the red buckets provided.</p>

    <div class="figrow">
      <figure><img src="../assets/img/amenities/basketball.jpg" alt="Basketball court near the Clubhouse"><figcaption>Basketball and pickleball court</figcaption></figure>
      <figure><img src="../assets/img/amenities/playground-swings.jpg" alt="Swings at North Beach"><figcaption>Swings at North Beach</figcaption></figure>
      <figure><img src="../assets/img/amenities/playground-horseshoes.jpg" alt="Horseshoe pits at North Beach"><figcaption>Horseshoes at North Beach</figcaption></figure>
    </div>
  </div></div></section>""")

amenity("picnic-shelters.html","Picnic Shelters","Picnic Shelters","assets/img/pages/spit-firepit.jpg",
 "Facilities for picnics, gatherings, or just a spot to relax and enjoy nature.",
 """  <section class="article"><div class="wrap"><div class="prose">
    <p>Enjoy our many facilities for picnics, gatherings, or just a spot to relax. The shelters and picnic areas are for residents and their invited guests. Four of these areas have covered shelters with fireplaces: North Beach, the Marina, the Clubhouse gazebo, and north of the Spit tennis courts. For current owners, shelters can be reserved through the amenity booking service in the <a href="https://app.condocontrol.com/login" target="_blank" rel="noopener">Owner Portal</a>; reservations are non-exclusive, so a reserved shelter remains available to other residents and their invited guests. Restrooms are available near all of the shelters.</p>
    <h2>North Beach</h2>
    <p>Our largest picnic area, with a covered fireplace, running water, propane barbeque, sink, stovetop, electrical outlet and picnic tables. Horseshoe pits, swings and restrooms are nearby.</p>
    <div class="figrow two">
      <figure><img src="../assets/img/amenities/north-beach-gazebo.jpg" alt="The gazebo at North Beach"><figcaption>The North Beach gazebo and picnic area.</figcaption></figure>
      <figure><img src="../assets/img/pages/picnic-shelter-winter.jpg" alt="A picnic shelter on a frosty morning"><figcaption>A covered shelter on a frosty morning by the water.</figcaption></figure>
    </div>
    <h2>Clubhouse Gazebo</h2>
    <p>A covered fireplace, electrical outlets, picnic tables and an overhead light, with the playground and pool just steps away.</p>
    <h2>Indian Cove (West Beach / Marina)</h2>
    <p>Steps from the marina docks, with a sink, stovetop, picnic tables, electrical outlets, string lights in the rafters and an outdoor fireplace.</p>
    <h2>Cuttysark Estuary (South Beach)</h2>
    <p>A single picnic table, with a restroom nearby.</p>
    <h2>The Spit</h2>
    <p>Next to the tennis courts, small and intimate, with running water, stovetop, propane barbeque, electrical outlet, covered fireplace and picnic tables.</p>
    <div class="callout"><p>Reserve a facility through the amenity booking service in the <a href="https://app.condocontrol.com/login" target="_blank" rel="noopener">Owner Portal</a>.</p></div>
  </div></div></section>""")

amenity("trails.html","Trails","Trails","assets/img/amenities/trails.jpg",
 "About 5.5 miles of marked trails through the major ravines and along the east and west banks.",
 """  <section class="article"><div class="wrap"><div class="split">
    <div class="prose">
      <p>Enjoy our trails, through the major ravines and along the east and west banks. Trail maps are available at the office, and the trails are clearly marked with signage.</p>
      <h3>Before you set out</h3>
      <ul>
        <li>The bluffs are actively eroding in places. Where you see a guard rail, it marks a spot to keep well back from, so please stay on the trail.</li>
        <li>Expect roots and loose rock underfoot. Bring water, and a walking companion is always a good idea.</li>
        <li>The trails are for walking, so please leave bikes and motorized vehicles off them, and keep dogs on leash.</li>
      </ul>

      <h2>Featured trails</h2>
      <h3>West Bluff &amp; Nature Trail</h3>
      <p>More ups and downs than the east side, a walking stick may help on the steeper hills. On clear days there are views of the Olympic Mountains. Known as the Nature Trail, signs along the way describe the trees and vegetation common at the Pointe, a project of resident and biologist Jim Cary.</p>
      <figure><img src="../assets/img/amenities/nature-trail-sign.jpg" alt="Interpretive sign along the Nature Trail"><figcaption>Interpretive signs along the Nature Trail describe the Pointe's trees and vegetation.</figcaption></figure>
      <h3>Indian Cove Trail</h3>
      <p>Park at the Clubhouse and walk down Pointes Drive West to the trailhead. Enjoy the ferny walk downhill to the bridge and across to the marina. Bring a snack and watch the marina at rest before retracing your steps up to Promontory Road.</p>
      <h3>East Bluff Trail</h3>
      <p>A mostly level trail, soft and spongy underfoot and open enough to see many forest and water birds. There are views across the water to Mount Rainier and benches to sit upon. Its northern end accesses the spit, or take the Lagoon Trail to North Beach and pick up the West Bluff Trail.</p>
      <h3>Cutty Sark &amp; Deep Ravine Trails</h3>
      <p>Multiple access points along Nantucket and Pointes Drive East reach the ravine, South Lagoon and South Beach. This is as close to an old-growth environment as we have at the Pointe, old trees, moss and a creek, with little development.</p>
    </div>
    <aside class="aside">
      <h4>Trail maps &amp; guides</h4>
      <ul>
        <li><a href="../assets/docs/trail-map.pdf" target="_blank" rel="noopener">Hartstene Pointe Trail Map<span class="doc-tag">PDF</span></a></li>
      </ul>
      <h4 style="margin-top:20px">The trail network</h4>
      <ul>
        <li>Marina Overlook &middot; East Bluff</li>
        <li>Big Tree &middot; Lagoon</li>
        <li>Promontory Switchback</li>
        <li>Portage Beach &middot; Marina Access</li>
        <li>South Lagoon &middot; Indian Cove</li>
        <li>Deep Ravine &middot; West Bluff</li>
        <li>Cutty Sark</li>
      </ul>
    </aside>
  </div></div></section>""")

amenity("pea-patch.html","Pea Patch","Pea Patch Garden","assets/img/amenities/pea-patch.jpg",
 "A community garden started in 2006 by owners with a shared vision.",
 """  <section class="article"><div class="wrap"><div class="prose">
    <p>The Pea Patch began in 2006 with a handful of property owners and a shared vision: a community garden in the sunny, partially fenced clearing behind the tennis court near the Clubhouse, home at the time to the horseshoe pit.</p>
    <p>The horseshoes found a fitting new home at the North Beach picnic area, and the gardeners set to work. Neighbors flipped pancakes at fundraising breakfasts to help pay for the new fencing, and the founding gardeners saw to the rest, laying out cedar-plank beds and filling them with good garden soil. That spirit carries on today: the garden is sustained by the annual dues of the owners who tend its plots, keeping the Pea Patch growing season after season.</p>
    <figure><img src="../assets/img/amenities/pea-patch.jpg" alt="The Pea Patch community garden"></figure>
    <div class="callout"><h4>A garden grown by volunteers</h4><p>The Pea Patch Committee, made up of owner volunteers, cares for the garden and its charter. For current owners, garden plots are arranged through the HPMA office.</p></div>
  </div></div></section>""")

amenity("wildlife.html","Wildlife","Wildlife &amp; Habitat","assets/img/amenities/wildlife.jpg",
 "The deer, eagles, shorebirds and wildflowers that make their home alongside us.",
 """  <section class="article"><div class="wrap"><div class="prose">
    <p>One of the quiet joys of life at the Pointe is the company we keep. Black-tailed deer step through the greenbelt at first light, fawns curl into the tall grass by midsummer, bald eagles wheel over the water and nest in the high firs, and shorebirds work the beaches at every low tide. The forest and shoreline that surround us are a living habitat, and its residents were here long before we were. Watching them, quietly and from a respectful distance, is one of the simplest pleasures the community offers.</p>

    <figure><img src="../assets/img/wildlife/doe.jpg" alt="A black-tailed doe and yearling in the golden light at Hartstene Pointe"><figcaption>Black-tailed deer are a familiar sight throughout the Pointe.</figcaption></figure>
    <div class="figrow">
      <figure><img src="../assets/img/wildlife/fawns.jpg" alt="Two spotted fawns in the grass at Hartstene Pointe"><figcaption>Fawns in the greenbelt in early summer.</figcaption></figure>
      <figure><img src="../assets/img/wildlife/eagle.jpg" alt="A bald eagle perched in a shoreline tree"><figcaption>Bald eagles nest and hunt along the shoreline.</figcaption></figure>
      <figure><img src="../assets/img/wildlife/sea-star.jpg" alt="An orange sea star in a tide pool at low water"><figcaption>Sea stars and shellfish in the tide pools at low tide.</figcaption></figure>
    </div>
    <figure><img src="../assets/img/wildlife/sandpipers.jpg" alt="Sandpipers along the beach at Hartstene Pointe"><figcaption>Shorebirds gather along the beaches at low tide.</figcaption></figure>

    <h2>Visitors from the Sound</h2>
    <p>The water brings its own parade. Harbor seals haul out on the boom logs to warm themselves, and on a lucky day a pod of orcas passes through close enough to hear the blow before you spot the fin.</p>
    <div class="figrow two">
      <figure><img src="../assets/img/wildlife/orcas.jpg" alt="Two orcas surfacing close to the forested shoreline near Hartstene Pointe"><figcaption>Orcas passing the Pointe, close enough to hear the blow.</figcaption></figure>
      <figure><img src="../assets/img/wildlife/seal.jpg" alt="A harbor seal hauled out on a boom log"><figcaption>A harbor seal warming itself on a boom log.</figcaption></figure>
    </div>

    <h2>The Pointe's wildflowers</h2>
    <p>The greenbelt does not feature an abundance of flowers, probably due to deer browsing, but we do have some:</p>
    <ul>
      <li><strong>Twinflower</strong>, moist shady areas, tiny flowers close to the ground; blooms all summer.</li>
      <li><strong>Orange &amp; hairy honeysuckle</strong>, vines among trailside brush; prefers partial shade; blooms late spring to early summer.</li>
      <li><strong>Red Indian paintbrush</strong>, dry environments, high on the bluffs north of the Bo'sun stairs in summer.</li>
      <li><strong>Columbia tiger lily</strong>, shady, moist places, May to August; a spectacular flower, please leave it for the next person to enjoy.</li>
      <li><strong>Yellow violets</strong>, very low-growing, along shady moist trails in spring and early summer.</li>
    </ul>
    <div class="figrow">
      <figure><img src="../assets/img/wildlife/twinflower.jpg" alt="Twinflower"><figcaption>Twinflower</figcaption></figure>
      <figure><img src="../assets/img/wildlife/orange-honeysuckle.jpg" alt="Orange honeysuckle"><figcaption>Orange honeysuckle</figcaption></figure>
      <figure><img src="../assets/img/wildlife/red-indian-paintbrush.jpg" alt="Red Indian paintbrush"><figcaption>Red Indian paintbrush</figcaption></figure>
      <figure><img src="../assets/img/wildlife/columbia-tiger-lily.jpg" alt="Columbia tiger lily"><figcaption>Columbia tiger lily</figcaption></figure>
      <figure><img src="../assets/img/wildlife/yellow-violets.jpg" alt="Yellow violets"><figcaption>Yellow violets</figcaption></figure>
    </div>

    <h2>Living alongside our wildlife</h2>
    <p>The Pointe is their home as much as ours, and a few small habits keep it healthy for everyone, wild and human alike.</p>
    <p><strong>Please don't feed the wildlife.</strong> Foods that aren't part of an animal's natural diet, corn, apples, bread and store-bought feed, can upset its digestion and do real harm. A well-meant handout can leave an animal worse off than none at all, so it is kindest to let them forage as they are meant to.</p>
    <p><strong>Give raccoons their space.</strong> Clever and endearing as they are, raccoons can carry diseases passed through contact with them or their waste. Enjoy them from a distance rather than handling them, and if you are ever bitten, scratched or exposed to their waste, check with a physician.</p>
    <figure><img src="../assets/img/wildlife/raccoon.jpg" alt="A raccoon at Hartstene Pointe"><figcaption>Raccoons are best enjoyed from a distance.</figcaption></figure>
    <div class="callout"><h4>A note on cougars</h4><p>Cougars are seen on the Pointe's trails from time to time. They are shy by nature and rarely a concern, but a few sensible precautions keep everyone comfortable: keep small children close and indoors by dusk, feed pets indoors and bring cats and dogs in from dusk to dawn, close off the spaces beneath porches and decks, and use garbage cans with tight-fitting lids. Because predators follow prey, not feeding the wildlife helps here too.</p></div>
  </div></div></section>""")

# ============ VISITING (guest / renter rules) ============
page("visiting/index.html", "Visiting the Pointe", "Visiting the Pointe",
     [home_link(), "Visiting"],
     herobg="assets/img/amenities/marina.jpg",
     lede="Welcome to Hartstene Pointe. We're so glad you're here, and hope you have a wonderful stay.",
     body="""  <section class="article"><div class="wrap"><div class="prose">
    <p>If you are staying with us as a guest or renter, your host has arranged everything you need. The Pointe is a quiet, wooded community wrapped in three and a half miles of private beach, and a little shared care keeps it that way for everyone, neighbors, guests and the deer and eagles alike. Here are a few friendly notes to help you settle in and make the most of your time here.</p>

    <h2>Settling in</h2>
    <ul>
      <li>Please take the roads at an easy <strong>15 mph</strong>. Children, dogs, deer and the occasional wandering fawn all share them.</li>
      <li>Sound carries in the quiet of the forest, so evenings are for keeping things mellow and outside lights low.</li>
      <li>There's room to park on the paved roads; please leave the grass, driveways and homes clear for your neighbors.</li>
    </ul>

    <h2>Enjoying the outdoors</h2>
    <ul>
      <li>Campfires are a treat at the Spit fire pits and the picnic-shelter fireplaces. When a burn ban is posted at the gate, we let the fires rest for a while.</li>
      <li>For the comfort of others and the safety of the forest, the Pointe is happily smoke-free and firework-free.</li>
      <li>Household garbage goes in the dumpsters just west of the Clubhouse.</li>
    </ul>

    <h2>Four-legged and wild neighbors</h2>
    <ul>
      <li>Keep dogs on a leash and pick up after them; waste bags go in the trash bins or dumpsters.</li>
      <li>Please don't feed the wildlife. It does them more harm than good, and they forage beautifully on their own. Our <a href="../amenities/wildlife.html">Wildlife &amp; Habitat</a> page introduces the animals you might meet.</li>
    </ul>

    <div class="callout"><h4>Questions during your stay?</h4><p>Your host is the best first stop for anything about the home you're in and its amenities, and can reach the HPMA office whenever it's needed.</p></div>

    <p style="margin-top:24px">Thank you for treating the Pointe with the same care the neighbors here do. Relax, breathe the salt air, and enjoy every minute.</p>
  </div></div></section>""")

# ============ COMMUNITY ============
page("community/index.html", "Community", "Community",
     [home_link(), "Community"],
     lede="A place to be part of something, or simply to be by yourself and enjoy the natural world.",
     body="""  <section class="article"><div class="wrap"><div class="prose">
    <p>Hartstene Pointe is a community, but also a place where people can be by themselves and enjoy the natural environment. No one is pressured to take part, and everyone is welcome to: neighbors join together in activities and governance as much, or as little, as suits them. It's your choice.</p>

    <h2>Take part in governance</h2>
    <p>Many people at the Pointe volunteer to join the Board of Directors, Board committees or ad-hoc committees, or simply lend their voice to governance issues. We encourage owners to do this: we are all stewards of the Pointe, and the community is better for every voice and helping hand. Learn more on the <a href="../governance/">Governance</a> and <a href="../governance/committees.html">Committees</a> pages.</p>

    <h2>Activities at the Pointe</h2>
    <p>Most activities are initiated and organized by volunteers or ad-hoc groups. Participating in social and recreational activities is an excellent way to connect with your neighbors, no pressure, no expectations, just do what is comfortable for you.</p>
    <div class="grid-2">
      <div class="callout"><h4>Recurring gatherings</h4><p>Book clubs &middot; Library group &middot; Walking groups &middot; News &amp; Views &middot; Pot-luck dinners &middot; Travel club &middot; Yoga &middot; Music circle</p></div>
      <div class="callout"><h4>Occasional events</h4><p>Holiday celebrations &amp; the 4th of July &middot; Fishing derby &middot; Marina salmon roast &middot; Garage sales &middot; Art exhibits &amp; fairs &middot; Concerts at North Beach</p></div>
    </div>
    <div class="figrow two">
      <figure><img src="../assets/img/pages/pie-social.jpg" alt="A community pie social at Hartstene Pointe"><figcaption>A community pie social.</figcaption></figure>
      <figure><img src="../assets/img/pages/community-bubbles.jpg" alt="A community gathering at Hartstene Pointe"><figcaption>Neighbors and families gather at a community event.</figcaption></figure>
    </div>
    <p style="margin-top:24px">See the community in pictures on our <a href="../photos/">Photos</a> page.</p>
  </div></div></section>""")

page("community/exploring-the-area.html", "Exploring the Area", "Exploring the Area",
     [home_link(), '<a href="index.html">Community</a>', "Exploring the Area"],
     herobg="assets/img/pages/driftwood-beach.jpg",
     lede="Marine parks, warm-water beaches, world-class shellfish and small-town character, all within an easy drive or a short paddle of the Pointe.",
     body="""  <section class="article"><div class="wrap"><div class="prose">
    <p>One of the pleasures of the Pointe is how much there is to explore just beyond the gate. Harstine Island and the Hood Canal are among the quietest, most beautiful corners of the Pacific Northwest. Here are a few favorites to help you plan a day out.</p>

    <div class="callout"><h4>Good to know</h4><p>These are independent parks and businesses, not affiliated with the Association. Hours, seasons and access change, so it is worth checking ahead before you go. Several of the marine parks are best reached by boat or at low tide.</p></div>

    <h2>On and around the island</h2>
    <ul>
      <li><strong>Jarrell Cove State Park</strong> (north end of Harstine Island). A 43-acre marine park in deeply protected water, with more than 650 feet of moorage, overnight docks, short forested walking loops, picnic shelters and playfields. A longtime favorite of boaters.</li>
      <li><strong>Harstine Island State Park</strong> (east shore). A quiet, undeveloped park where trails wind through mature Douglas fir and fern before dropping to a long, uncrowded beach. Good for hiking, beachcombing and birdwatching; dogs are restricted to protect wildlife.</li>
      <li><strong>McMicken Island State Park</strong> (just offshore). A small, primitive marine park linked to Harstine by a sand spit that emerges only at very low tide. Popular with kayakers and boaters. Check the tide charts before crossing on foot.</li>
      <li><strong>Stretch Point State Park</strong> (boat-in). A small marine park with one of the area's nicer swimming beaches.</li>
      <li><strong>Wild Felid Advocacy Center</strong> (on the island). A wild-cat sanctuary that is home to roughly 60 cats, open to visitors on scheduled tours.</li>
    </ul>

    <h2>Shellfish and dining along the Hood Canal</h2>
    <p>The cold, clean water of the Hood Canal produces some of the finest oysters, clams and geoduck anywhere. A loop around the canal strings together several of the region's best-known tables.</p>
    <ul>
      <li><strong>Taylor Shellfish Farms</strong> (Shelton). The flagship retail store of the region's best-known shellfish grower. Buy oysters, clams, crab and geoduck straight from the source, with outdoor picnic tables for a casual, self-shucked lunch.</li>
      <li><strong>Hama Hama Oyster Saloon</strong> (Lilliwaup). An outdoor, farm-to-table oyster house on the tide flats, serving wood-roasted and raw oysters steps from where they are harvested. Seasonal, with a Farm Store open year-round.</li>
      <li><strong>Alderbrook Resort &amp; Spa</strong> (Union). A historic waterfront lodge and spa on the Hood Canal, with a well-regarded restaurant, full spa, indoor pool and a guest marina. A comfortable base or a special dinner out.</li>
      <li><strong>The Fjord Oyster Bank</strong> (Hoodsport). A small, much-loved seafood restaurant carrying on the recipes of legendary local chef Xinh Dwelley, known for its chowder and oyster dishes.</li>
      <li><strong>Hood Canal&eacute;</strong> (Union). A cozy wood-fired pizza kitchen and wine shop in the waterfront village of Union, with Pacific Northwest wines and the occasional evening of live music.</li>
    </ul>

    <h2>Parks, trails and landmarks</h2>
    <ul>
      <li><strong>Twanoh State Park</strong> (Union). Some of the warmest saltwater beaches in the state, plus a two-mile forested loop along salmon-bearing Twanoh Creek and rustic stone shelters built by the Civilian Conservation Corps in the 1930s.</li>
      <li><strong>Theler Wetlands</strong> (Belfair). A flat, accessible network of gravel paths and boardwalks crossing tidal marsh at the head of the canal, and one of the South Sound's premier birdwatching spots for herons, eagles and otters.</li>
      <li><strong>High Steel Bridge</strong> (northwest of Shelton). A former logging railroad bridge standing about 375 feet above the South Fork Skokomish River canyon, one of the highest bridges of its kind in the country, with dramatic views into the gorge below.</li>
      <li><strong>Olympic National Park and National Forest</strong> (west of Shelton). Mountain trails, temperate rainforest, waterfalls and sweeping vistas, all within an easy drive.</li>
    </ul>

    <h2>In and around Shelton</h2>
    <ul>
      <li><strong>Skyline Drive-In Theater</strong> (Shelton). One of only a handful of drive-in theaters left in Washington, showing weekend double features under the stars in season. A fun, family-friendly evening.</li>
      <li><strong>Shelton</strong> (about 18 miles, the county seat). The nearest full-service town, with groceries, fuel, hardware, medical care and everyday dining.</li>
    </ul>

    <p style="margin-top:24px">Closer to home, the Pointe's own beaches, trails and marina are described on the <a href="../amenities/">Amenities</a> pages, and there is more on the island's past on the <a href="../about/history.html">Our Stories &amp; History</a> page.</p>
  </div></div></section>""")

page("community/considering-the-pointe.html", "Considering the Pointe", "Considering the Pointe",
     [home_link(), '<a href="index.html">Community</a>', "Considering the Pointe"],
     herobg="assets/img/pages/aerial-clubhouse.jpg",
     desc="Thinking of buying at Hartstene Pointe? How this private, gated 532-home community on Harstine Island, WA works: HOA governance, assessments, amenities, CC&Rs, and marina slips.",
     lede="Thinking about a home at the Pointe? Here is what the community is, how it works, and where to find the details.",
     body="""  <section class="article"><div class="wrap"><div class="split">
    <div class="prose">
      <p>If you are considering a home at Hartstene Pointe, this page is here to help you understand the community and how it works. The Association does not sell or list homes and cannot discuss specific properties; for homes on the market, please work with a licensed real estate professional. What we can do is explain what it means to own here.</p>

      <h2>What Hartstene Pointe is</h2>
      <p>Hartstene Pointe is a private, gated community on the northern tip of Harstine Island in Mason County, Washington, reached by a toll-free bridge off Highway 3 with no ferry to schedule. Established by Weyerhaeuser as a not-for-profit corporation in 1970, it is made up of 532 home sites, including the Island House condominiums, spread across roughly 215 wooded acres and surrounded on three sides by the waters of Puget Sound. Once planned mainly as a recreational retreat, the Pointe today is a mix of full-time residents and seasonal owners.</p>

      <h2>How the community works</h2>
      <p>Every owner is a member of the Hartstene Pointe Maintenance Association. The community is governed by a seven-member Board of Directors elected by owners, and run day to day by a professional General Manager with office, patrol and maintenance staff. Ownership comes with both a voice in how the Pointe is run and a shared responsibility to help care for it. There is more on the <a href="../governance/">Governance</a> page.</p>

      <h2>What your assessments support</h2>
      <p>Annual assessments paid by owners maintain the private roads, the gated entrance and patrol, and the common greenbelt and beaches, and they fund the shared amenities that make the Pointe what it is:</p>
      <ul>
        <li>A 6,000-square-foot Clubhouse with a library</li>
        <li>A swimming pool and spa, a fitness center, and courts for tennis, pickleball and basketball</li>
        <li>A playground and picnic areas</li>
        <li>5.5 miles of walking trails through the woods</li>
        <li>Two boat launches</li>
        <li>3.5 miles of private beach and common shoreline</li>
      </ul>
      <p>A few amenities support themselves: the 110-slip marina and the Pea Patch garden are funded by the moorage assessments and plot dues of the owners who use them, at no cost to the wider Association.</p>
      <p>Assessment amounts are set each year by the Board. For current figures, and for any special assessments, contact the <a href="../contact/">HPMA office</a>.</p>

      <h2>Water and sewer</h2>
      <p>Water and sewer service is provided by the Hartstene Pointe Water-Sewer District, a separate government entity that is not run by the Association and is billed separately. Questions about rates and service go directly to the District at <a href="https://www.hpwsd.org/" target="_blank" rel="noopener">hpwsd.org</a>.</p>

      <h2>Building, remodeling and trees</h2>
      <p>To protect the wooded character of the Pointe, most changes to a property are reviewed by the Permit Review Committee, from new construction and additions to exterior painting and tree cutting. If you are buying with a project in mind, review the CC&amp;Rs that apply to your lot before you commit. The CC&amp;Rs differ between plats, so be sure you are reading the set for your property.</p>

      <h2>The marina</h2>
      <p>Indian Cove Marina is an owner amenity, and there is no public or transient moorage. All slips are privately held: they are leased long-term and are bought, sold or sublet only among Hartstene Pointe lot owners, so owning a lot at the Pointe comes first. See the <a href="../amenities/marina.html">Marina</a> page for details.</p>

      <h2>If you plan to rent your home</h2>
      <p>Some owners rent their homes when they are away. Renters and their guests are expected to follow the community's Rules &amp; Regulations, summarized for visitors on the <a href="../visiting/">Visiting the Pointe</a> page. If rental income is part of your plans, review the current rules with the office first.</p>

      <h2>Doing your homework</h2>
      <p>Before you buy, it is worth reviewing the documents that govern life at the Pointe. Most are posted on the <a href="../governance/documents.html">Governing Documents</a> page, and the office can help with anything not listed there:</p>
      <ul>
        <li>The CC&amp;Rs for your specific plat</li>
        <li>The Bylaws and the Rules &amp; Regulations</li>
        <li>Current assessment amounts and any special assessments</li>
        <li>Marina moorage availability, if a slip matters to you</li>
        <li>Water and sewer rates from the District</li>
      </ul>

      <div class="callout"><h4>Questions about the community?</h4><p>The HPMA office is glad to answer general questions about how the Pointe works. Reach the office through our <a href="../contact/">contact page</a>. For homes currently for sale, a local real estate professional can help; the Association is not able to recommend agents or discuss specific listings.</p></div>
    </div>
    <aside class="aside">
      <h4>At a glance</h4>
      <div class="info-row"><b>Location</b><span>North tip of Harstine Island, Mason County, WA</span></div>
      <div class="info-row"><b>Access</b><span>Toll-free bridge off Highway 3, no ferry</span></div>
      <div class="info-row"><b>Established</b><span>1970, not-for-profit corporation</span></div>
      <div class="info-row"><b>Home sites</b><span>532, including Island House condominiums</span></div>
      <div class="info-row"><b>Setting</b><span>About 215 wooded acres, water on three sides</span></div>
      <div class="info-row"><b>Governance</b><span>Seven-member elected Board and a professional manager</span></div>
      <div class="info-row"><b>Nearest town</b><span>Shelton, about 18 miles</span></div>
      <h4 style="margin-top:22px">Start here</h4>
      <ul>
        <li><a href="index.html">About the community</a></li>
        <li><a href="../amenities/">Amenities</a></li>
        <li><a href="../governance/documents.html">Governing Documents</a></li>
        <li><a href="exploring-the-area.html">Exploring the area</a></li>
        <li><a href="../contact/">Contact the office</a></li>
      </ul>
    </aside>
  </div></div></section>""")

# ============ CONTACT ============
page("contact/index.html", "Contact", "Contact",
     [home_link(), "Contact"],
     lede="The HPMA office is here to help owners, residents and guests.",
     body="""  <section class="article"><div class="wrap">
    <div class="contact-grid">
      <div class="contact-card">
        <h3>HPMA Office</h3>
        <div class="line"><b>Address</b><span>202 E Pointes Dr. East<br>Shelton, WA 98584</span></div>
        <div class="line"><b>Phone</b><span><a href="tel:+13604262300">(360) 426-2300</a></span></div>
        <div class="line"><b>Fax</b><span>(360) 427-6208</span></div>
        <div class="line"><b>Email</b><span><a href="mailto:office@hpma.org">office@hpma.org</a></span></div>
        <div class="line"><b>General Manager</b><span><a href="tel:+13606145072">(360) 614-5072</a><br><a href="mailto:derek@hpma.org">derek@hpma.org</a></span></div>
        <div class="line"><b>Hours</b><span>Mon&ndash;Fri 8:30am&ndash;5:00pm<br>Saturday 10:00am&ndash;Noon</span></div>
      </div>
      <div class="contact-card">
        <h3>Marina &amp; other contacts</h3>
        <div class="line"><b>Harbormaster</b><span><a href="tel:+13602293137">(360) 229-3137</a><br><a href="mailto:harbormaster@hpma.org">harbormaster@hpma.org</a></span></div>
        <div class="line"><b>Water &amp; Sewer</b><span>Hartstene Pointe Water-Sewer District<br><a href="tel:+13604272413">(360) 427-2413</a> &middot; <a href="mailto:acct@hpwsd.org">acct@hpwsd.org</a><br><a href="https://www.hpwsd.org/" target="_blank" rel="noopener">hpwsd.org &#8599;</a></span></div>
        <div class="line"><b>Owner Portal</b><span>Pay dues &amp; manage your account<br><a href="https://app.condocontrol.com/login" target="_blank" rel="noopener">Sign in to Condo Control &#8599;</a></span></div>
      </div>
    </div>
    <div class="callout" style="margin-top:30px"><p>The Water-Sewer District is a separate government entity and is not run by Hartstene Pointe. For water and sewer service or billing questions, please contact the District directly.</p></div>
  </div></section>""")

# ============ PHOTO GALLERY ============
# Albums mirror the original hpma.org Photo Gallery. Data lives in
# _tools/gallery-albums.json (scraped once from the old site: image file,
# title, and photographer credit). Every image maps to exactly one album.
GAL = os.path.join(ROOT, "assets", "img", "gallery")
with open(os.path.join(os.path.dirname(__file__), "gallery-albums.json"), encoding="utf-8") as _f:
    ALBUMS = json.load(_f)

# short blurb per album, keyed by id
ALBUM_BLURB = {
    100: "A selection of favorite scenes from around the community, the water, the marina, and life at the Pointe.",
    13: "A December king tide that pushed the Sound right up to the picnic tables and pathways.",
    2:  "Fir and madrona, eagles and deer, tide pools and wildflowers: the natural life of the peninsula.",
    9:  "Neighbors, gatherings, and everyday life around the Pointe.",
    5:  "Sunrises, sunsets, and the ever-changing sky over Puget Sound.",
    14: "The quiet lagoon at the North Beach, a favorite spot for kayakers and herons.",
}

def caption(p):
    t, c = p.get("title", "").strip(), p.get("credit", "").strip()
    if t and c:
        return f"{t}. Photo: {c}"
    if c:
        return f"Photo: {c}"
    return t

def gallery_block(alb):
    tiles = ""
    for p in alb["photos"]:
        f = html.escape(p["file"])
        cap = html.escape(caption(p), quote=True)
        alt = html.escape(caption(p) or "Hartstene Pointe")
        tiles += (f'      <a href="../assets/img/gallery/{f}" data-caption="{cap}">'
                  f'<img loading="lazy" src="../assets/img/gallery/{f}" alt="{alt}"></a>\n')
    n = len(alb["photos"])
    blurb = ALBUM_BLURB.get(alb["id"], "")
    return (f'    <div class="album">\n'
            f'      <div class="album-head"><h2>{html.escape(alb["name"])}</h2>'
            f'<span class="album-count">{n} photos</span></div>\n'
            f'      {"<p class=\"album-blurb\">" + html.escape(blurb) + "</p>" if blurb else ""}\n'
            f'      <div class="gallery">\n{tiles}      </div>\n'
            f'    </div>\n')

# quick jump nav across albums
_jump = " ".join(
    f'<a href="#album-{a["id"]}">{html.escape(a["name"])}</a>' for a in ALBUMS)
_sections = ""
for a in ALBUMS:
    _sections += f'  <section class="article album-section" id="album-{a["id"]}"><div class="wrap">\n{gallery_block(a)}</div></section>\n'

_total = sum(len(a["photos"]) for a in ALBUMS)
page("photos/index.html", "Photos", "Photo Gallery",
     [home_link(), "Photos"],
     lede=f"Scenes from around the Pointe, contributed by residents over the years: {_total} photographs across {len(ALBUMS)} albums. Click any photo to view it larger.",
     body=f'  <div class="album-jump"><div class="wrap"><span>Albums:</span> {_jump}</div></div>\n{_sections}')

# ------------------------------------------------------------------ SITEMAP
_sm = ['<?xml version="1.0" encoding="UTF-8"?>',
       '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
       f'  <url><loc>{SITE}/</loc></url>']
_sm += [f'  <url><loc>{u}</loc></url>' for u in WRITTEN]
_sm.append('</urlset>')
with open(os.path.join(ROOT, "sitemap.xml"), "w", encoding="utf-8") as f:
    f.write("\n".join(_sm) + "\n")
print("wrote sitemap.xml")

print("ALL PAGES DONE")

