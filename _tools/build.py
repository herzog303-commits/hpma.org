# -*- coding: utf-8 -*-
"""Static-site generator for hpma.org. Emits plain HTML files (no runtime dep)."""
import os, glob, html

# Repo root = parent of this _tools/ folder, so the script is portable.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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
    <li><a href="{p}community/">Community</a></li>
    <li><a href="{p}photos/">Photos</a></li>
    <li><a href="https://app.condocontrol.com/login" class="portal" target="_blank" rel="noopener">Owner Portal</a></li>
  </ul>"""

HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} &middot; Hartstene Pointe</title>
<meta name="description" content="{desc}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<link rel="icon" type="image/jpeg" href="{p}assets/img/logo.jpg">
<link rel="apple-touch-icon" href="{p}assets/img/logo.jpg">
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
    <img class="brand-mark" src="{p}assets/img/logo.jpg" alt="Hartstene Pointe crest" width="42" height="43">
    <span class="wm">HARTSTENE POINTE</span>
  </a>
  <button class="nav-toggle" aria-label="Menu" aria-expanded="false"><span></span><span></span><span></span></button>
{nav}
</nav>

<main id="main">
  <header class="page-hero">
    <div class="bg" style="background-image:url('{p}{herobg}')"></div>
    <div class="wrap">
      <nav class="crumbs">{crumbs}</nav>
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
        <img class="foot-mark" src="{p}assets/img/logo.jpg" alt="Hartstene Pointe crest" width="38" height="39">
        <div class="wm">HARTSTENE POINTE</div>
        <div class="sub">Maintenance Association</div>
        <p>202 E Pointes Dr. East<br>Shelton, WA 98584<br>(360) 426&ndash;2300<br><a href="mailto:office@hpma.org">office@hpma.org</a></p>
      </div>
      <div><h4>Explore</h4><ul>
        <li><a href="{p}amenities/">Amenities</a></li>
        <li><a href="{p}amenities/trails.html">Trails</a></li>
        <li><a href="{p}amenities/marina.html">Marina</a></li>
        <li><a href="{p}photos/">Photos</a></li>
      </ul></div>
      <div><h4>Association</h4><ul>
        <li><a href="{p}about/">About</a></li>
        <li><a href="{p}governance/">Governance</a></li>
        <li><a href="{p}governance/documents.html">Governing Documents</a></li>
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
    out = HEAD.format(title=html.escape(title), desc=html.escape(desc or h1), p=p,
                      nav=NAV.format(p=p), herobg=herobg, crumbs=crumb_html,
                      h1=h1, lede=lede_html)
    out += "\n" + body + "\n"
    out += FOOT.format(p=p)
    full = os.path.join(ROOT, path.replace("/", os.sep))
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(out)
    print("wrote", path)

def home_link(depth=1):
    return f'<a href="{"../"*depth}index.html">Home</a>'

# ------------------------------------------------------------------ PAGES

# ============ ABOUT ============
page("about/index.html", "About the Pointe", "About the Pointe",
     [home_link(), "About"],
     herobg="assets/img/hero-marina.jpg",
     lede="A unique community on the northern tip of Harstine Island, set within a verdant forest and surrounded on three sides by the waters of Puget Sound.",
     body="""  <section class="article"><div class="wrap"><div class="split">
    <div class="prose">
      <p>Hartstene Pointe is a unique community located on the northern tip of Harstine Island, set within a verdant forest, and surrounded on three sides by the waters of Puget Sound. The Pointe is approximately 215 acres in size and is situated about 18 miles northeast of the City of Shelton in Mason County, Washington.</p>
      <p>In 1970 Weyerhaeuser established Hartstene Pointe as a not-for-profit corporation. While Hartstene Pointe was originally planned to be a recreational community, a significant number of the homes serve as primary residences today. The Pointe consists of 532 private residential lots, 90 of which are condominium &ldquo;Island Houses&rdquo;, along with a private road system, a 6,000&nbsp;sq.&nbsp;ft. Clubhouse, a swimming pool and hot tub, three tennis courts, a basketball court, a pickleball court, about 5.5 miles of walking trails, a 110-slip marina, a boat launch, picnic areas and 3.5 miles of private beach.</p>
      <p>Decades on, Hartstene Pointe remains heavily wooded with Douglas fir, hemlock, cedar, madrona, maple and various other deciduous trees. The area is also home to a significant population of birds, deer and raccoons, and bald eagles have been sighted along the water's edge. Along its perimeter, Hartstene Pointe gives magnificent views of Puget Sound, Mt. Rainier and the Olympic Mountains.</p>

      <h2>HPMA, the organization</h2>
      <p>&ldquo;The Pointe&rdquo; is incorporated as a non-profit homeowners' association, as described in our <a href="../governance/">Governance</a> section. HPMA is governed by a seven-member Board of Directors and administered by a General Manager and staff.</p>

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
      <div class="info-row"><b>Location</b><span>Harstine Island, Mason County, WA</span></div>
      <p style="margin-top:16px"><a class="btn ghost" href="our-place.html">Our Place &amp; maps</a></p>
    </aside>
  </div></div></section>""")

page("about/our-place.html", "Our Place", "Our Place",
     [home_link(), '<a href="index.html">About</a>', "Our Place"],
     lede="Where we are, how the island came to be, and what it's like to live at the Pointe.",
     body="""  <section class="article"><div class="wrap"><div class="prose">
    <h2>Harstine Island</h2>
    <p>Harstine Island, approximately ten miles long and three miles wide, is located at the southern end of Puget Sound, 18 miles away from the nearest town, Shelton. The island is accessible by a bridge from Highway 3 that links Shelton to Bremerton. Stories exist to explain the several spellings of Harstine / Hartstene.</p>
    <p>Lured by the quiet beauty and low cost of land, early settlers farmed, logged, planted orchards, and gathered clams and oysters from the sea. The settlers built schools and stores, and in 1914 volunteers erected the Community Hall, which is still actively used today. Electricity and telephone were not available on the island until 1947. A ferry provided transportation across the passage until 1969, when a bridge was built connecting the island to the mainland.</p>

    <h2>Hartstene Pointe</h2>
    <p>In 1970 Weyerhaeuser established Hartstene Pointe as a not-for-profit corporation. Located on the northern tip of the island, it is an unincorporated community of 532 home sites, surrounded by common green-belt property. While Hartstene Pointe was originally planned to be a recreational community, a significant share of the homes serve as primary residences today.</p>
    <p>The Pointe employs a full-time Manager, office, patrol and maintenance staff, and is governed by a seven-member Board of Directors elected by the property owners. The Board functions under the Covenants, Conditions and Restrictions (CC&amp;Rs). All development at the Pointe, including new construction, additions, exterior maintenance and painting, and tree cutting, is closely regulated by the Permit Review Committee.</p>
    <p>There is a 6,000-square-foot Clubhouse with a library, a swimming pool and spa, three tennis courts, a basketball court, a playground, a pickleball court, 5.5 miles of walking trails, a 110-slip marina, a boat launch, picnic areas and 3.5 miles of beach. The community remains heavily wooded with Douglas fir, hemlock, cedar, madrona and maple, and is home to deer, raccoons and many birds, with bald eagles sighted along the water's edge.</p>

    <h2>Where are we?</h2>
    <p>Hartstene Pointe is on the northern tip of Harstine Island in Mason County, Washington, reached by the Harstine Island bridge off Highway 3, about 18 miles from Shelton. Detailed community maps are available on the <a href="../governance/documents.html">Governing Documents</a> page and at the HPMA office.</p>

    <div class="callout warn"><h4>Be prepared</h4><p>Island living means being ready for weather, power outages and other events. The Association's Disaster Preparedness resources help owners plan ahead, see the emergency-preparedness materials in the office and on the <a href="../governance/committees.html">Committees</a> page.</p></div>
  </div></div></section>""")

page("about/history.html", "Our Stories &amp; History", "Our Stories &amp; History",
     [home_link(), '<a href="index.html">About</a>', "History"],
     lede="The people and memories behind the Pointe, gathered from residents past and present.",
     body="""  <section class="article"><div class="wrap"><div class="split">
    <div class="prose">
      <h2>Collective memories</h2>
      <p>Once upon a time, four would-be historians were struck by a sobering thought: most of the original residents from the 1970s had left, for one reason or another. As their numbers dwindled, so did the sources of the oral history of the beginnings of Hartstene Pointe.</p>
      <p>A plan was made to find them and listen to their stories. To support sometimes-contradictory accounts, some memories clear as a bell, others foggy in the details, they gleaned through the archives of board meetings, newsletters, correspondence, personal letters and lawsuits.</p>

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

      <h2>Contribute a story</h2>
      <p>We invite contributions of stories to enhance our history. Send them to the office via our <a href="../contact/">contact page</a>.</p>
    </div>
    <aside class="aside">
      <h4>Did you know?</h4>
      <div class="info-row"><b>Water, 1972</b><span>$1/month for undeveloped lots, $2 for lots with homes</span></div>
      <div class="info-row"><b>Sewer</b><span>$1 per lot, $5 for a home</span></div>
      <div class="info-row"><b>Dues</b><span>$8 a month</span></div>
      <div class="info-row"><b>Taxes</b><span>1.13% of market value</span></div>
    </aside>
  </div></div></section>""")

# ============ GOVERNANCE ============
page("governance/index.html", "Governance", "Governance",
     [home_link(), "Governance"],
     lede="How decisions are made at the Pointe, and how owners take part in making them.",
     body="""  <section class="article"><div class="wrap"><div class="split">
    <div class="prose">
      <p>Simply put, <em>governance</em> means the process of decision-making and the process by which decisions are implemented. It includes the formal and informal actors involved in making and carrying out decisions, and the structures set in place to arrive at and implement them.</p>

      <h2>Our formal structure</h2>
      <p>HPMA is governed as stated in our governing documents:</p>
      <ul>
        <li>Articles of Incorporation</li>
        <li>CC&amp;Rs (Covenants, Conditions &amp; Restrictions)</li>
        <li>Bylaws</li>
        <li>Rules &amp; Regulations</li>
      </ul>
      <p>You can read all of these on the <a href="documents.html">Governing Documents</a> page. The Board has also established several committees in the Bylaws; these committees advise the Board but are not delegated Board authority.</p>

      <h2>How it works in practice</h2>
      <p>Property owners elect a seven-member Board of Directors each June, with terms running three years, two or three seats come up for election each year. The Board elects its own officers: President, Vice-President, Secretary and Treasurer.</p>
      <p>The Board meets twice a month, on the 2nd Thursday and the 3rd Saturday. These meetings are open to property owners, not to the general public, guests, or prospective buyers. The Saturday meeting is where business affecting all property owners is conducted, and owners are urged to attend and participate. While owners are encouraged to present their views, the Board has the final decision-making authority.</p>

      <h2>The informal system</h2>
      <p>In addition to the formal system, the Pointe has a number of informal, ad-hoc committees, task forces, groups and individuals who are self-organizing and take on various roles within the community. These people are essential to foster the ongoing work and activities at the Pointe, and to inform the formal governance system on key issues.</p>
    </div>
    <aside class="aside">
      <h4>Board committees</h4>
      <ul>
        <li>Long Range Planning</li>
        <li>Permit Review</li>
        <li>Natural Resources / Common Area Stewardship</li>
        <li>Recreation</li>
        <li>Moorage</li>
        <li>Island House</li>
        <li>Fire Safety</li>
        <li>Emergency / Disaster Preparedness</li>
        <li>Pea Patch</li>
      </ul>
      <p style="margin-top:14px"><a class="btn ghost" href="committees.html">About committees</a></p>
    </aside>
  </div></div></section>""")

page("governance/committees.html", "Committees", "Committees",
     [home_link(), '<a href="index.html">Governance</a>', "Committees"],
     lede="Many owners volunteer to serve on committees that help the community in countless ways.",
     body="""  <section class="article"><div class="wrap"><div class="split">
    <div class="prose">
      <h2>The role of committees</h2>
      <p>Many people at the Pointe volunteer to serve on committees to help the community in various ways. Our Bylaws make provision for the Board to appoint advisory committees, sometimes called Standing Committees, which are expected to operate for an extended period with ongoing responsibilities and charges from the Board.</p>
      <p>The Bylaws set out, for all committees, their operating procedures, authority and duration; and for each committee, its membership requirements and scope of responsibility.</p>

      <h2>Ad-hoc committees</h2>
      <p>Some committees are established by the Board for a limited time or purpose, and others simply emerge on their own. Examples have included a Roads Committee and a Bluff Erosion group, along with many groups that form for a certain purpose and then disband when it is achieved.</p>

      <div class="callout"><h4>Get involved</h4><p>Interested in serving? Owners are always welcome. Contact the <a href="../contact/">HPMA office</a> to learn which committees are seeking volunteers.</p></div>
    </div>
    <aside class="aside">
      <h4>Board advisory committees</h4>
      <ul>
        <li>Permit Review</li>
        <li>Common Area Stewardship</li>
        <li>Disaster Preparedness</li>
        <li>Long Range Planning</li>
        <li>Fire Safety</li>
        <li>Pea Patch</li>
        <li>Island House</li>
        <li>Moorage</li>
        <li>Recreation</li>
      </ul>
      <h4 style="margin-top:20px">Ad-hoc examples</h4>
      <ul>
        <li>Roads Committee</li>
        <li>Bluff Erosion</li>
        <li>&hellip; and others that come &amp; go</li>
      </ul>
    </aside>
  </div></div></section>""")

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

    <h2>Forms &amp; maps</h2>
    <ul class="doclist">
      <li><a href="../assets/docs/facilities-use-application.pdf" target="_blank" rel="noopener"><span class="doc-ic">PDF</span>Facilities Use Application<span class="doc-note">Editable form</span></a></li>
      <li><a href="../assets/docs/map-1.pdf" target="_blank" rel="noopener"><span class="doc-ic">PDF</span>Hartstene Pointe Map 1</a></li>
      <li><a href="../assets/docs/map-2.pdf" target="_blank" rel="noopener"><span class="doc-ic">PDF</span>Hartstene Pointe Map 2</a></li>
    </ul>

    <div class="callout"><p>Looking for something not listed here? The <a href="../contact/">HPMA office</a> can help with Articles of Incorporation, additional plat CC&amp;Rs, and other records.</p></div>
  </div></div></section>"""
page("governance/documents.html", "Governing Documents", "Governing Documents",
     [home_link(), '<a href="index.html">Governance</a>', "Documents"],
     lede="Articles, CC&amp;Rs, Bylaws, Rules &amp; Regulations, moorage documents, forms and maps.",
     body=DOCS)

# ============ AMENITIES INDEX ============
AM = [
 ("clubhouse.html","Clubhouse","assets/img/amenities/clubhouse.jpg","6,000 sq. ft. of gathering space, a library, and the entrance to the pool."),
 ("pool-spa.html","Pool &amp; Spa","assets/img/amenities/pool.jpg","A swimming pool and hot tub with seasonal hours, steps from the Clubhouse."),
 ("marina.html","Marina","assets/img/amenities/marina.jpg","Indian Cove Marina, 110 slips, transient moorage, and two boat ramps."),
 ("boat-rv-storage.html","Boat &amp; RV Storage","assets/img/amenities/marina.jpg","On-site storage for boats, trailers, RVs, kayaks and canoes."),
 ("fitness-center.html","Fitness Center","assets/img/amenities/fitness.jpg","Open 24 hours with cardio machines, weights and more, gate card required."),
 ("outdoor-recreation.html","Outdoor Recreation","assets/img/amenities/recreation.jpg","Tennis, pickleball, basketball, playgrounds, horseshoes and fire pits."),
 ("picnic-shelters.html","Picnic Shelters","assets/img/amenities/picnic.jpg","Five picnic areas around the Pointe, from North Beach to the Spit."),
 ("trails.html","Trails","assets/img/amenities/trails.jpg","About 5.5 miles of marked trails through ravines and along the bluffs."),
 ("pea-patch.html","Pea Patch Garden","assets/img/amenities/pea-patch.jpg","A community garden started in 2006 by owners with a shared vision."),
 ("wildlife.html","Wildlife &amp; Habitat","assets/img/amenities/wildlife.jpg","Deer, eagles, raccoons and wildflowers, and how to coexist safely."),
]
cards = "".join(
 f'<a class="acard" href="{u}"><div class="ph" style="background-image:url(\'../{img}\')"></div>'
 f'<div class="bd"><h4>{t}</h4><p>{d}</p><span class="go">Explore &rarr;</span></div></a>\n'
 for (u,t,img,d) in AM)
page("amenities/index.html", "Amenities", "Amenities",
     [home_link(), "Amenities"],
     lede="HPMA is fortunate to have a wide range of amenities available to property owners. The General Manager oversees their maintenance, with advice from the Recreation, Moorage and Common Area Stewardship committees.",
     body=f'  <section class="article"><div class="wrap"><div class="grid-3">\n{cards}  </div></div></section>')

# ============ AMENITY SUB-PAGES ============
def amenity(u, title, h1, hero, lede, body):
    page("amenities/"+u, title, h1,
         [home_link(), '<a href="index.html">Amenities</a>', h1.replace("&amp;","&")],
         lede=lede, herobg=hero, body=body)

amenity("clubhouse.html","Clubhouse","Clubhouse","assets/img/amenities/clubhouse.jpg",
 "The heart of the community, 6,000 square feet of gathering space overlooking the Pointe.",
 """  <section class="article"><div class="wrap"><div class="split">
    <div class="prose">
      <p>The Hartstene Pointe Clubhouse offers something for everyone in the community.</p>
      <h3>Our Clubhouse offers</h3>
      <ul>
        <li>Manager and business office (for residents)</li>
        <li>Multi-purpose room, activities, meetings, ping pong, pool, chess and checkers</li>
        <li>Library, books, magazines, DVDs and puzzles</li>
        <li>Kitchen (for scheduled events)</li>
        <li>Bulletin boards and information posting</li>
        <li>An outside gazebo with fireplace, for meetings and events</li>
        <li>Entrance to the pool &amp; spa</li>
        <li>Free Wi-Fi</li>
      </ul>
      <h2>The Library</h2>
      <p>The Library is full of great reads, ranging from children's books and non-fiction to magazines and classic novels. All books are donated and may be checked out by all Pointe residents and their guests on an honor system. There are also games, puzzles and DVD and VCR movies. A team of volunteers maintains the Library for the benefit of the community.</p>
      <figure><img src="../assets/img/pages/clubhouse-2.jpg" alt="Hartstene Pointe Clubhouse"></figure>
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
      <p>The pool and spa are open to residents and their guests. Please read the pool and spa regulations before using the facilities.</p>
      <h3>Pool use considerations</h3>
      <ul>
        <li>Guests 12 and under must have an adult with them at the pool.</li>
        <li>Please observe posted quiet-swim and all-swim times.</li>
        <li>No reservation required.</li>
      </ul>
      <figure><img src="../assets/img/amenities/pool.jpg" alt="The pool at Hartstene Pointe"></figure>
    </div>
    <aside class="aside">
      <h4>Summer pool hours</h4>
      <p style="font-size:12px;color:var(--rock);margin-bottom:10px">Memorial weekend &ndash; Labor Day weekend</p>
      <div class="info-row"><b>Sun&ndash;Thu &middot; Quiet swim</b><span>9&ndash;10am &amp; 5&ndash;6pm</span></div>
      <div class="info-row"><b>Sun&ndash;Thu &middot; All swim</b><span>10am&ndash;5pm &amp; 6&ndash;9pm</span></div>
      <div class="info-row"><b>Fri&ndash;Sat &middot; Quiet swim</b><span>9&ndash;10am &amp; 5&ndash;6pm</span></div>
      <div class="info-row"><b>Fri&ndash;Sat &middot; All swim</b><span>10am&ndash;5pm &amp; 6&ndash;10pm</span></div>
    </aside>
  </div></div></section>""")

amenity("marina.html","Marina","Marina","assets/img/amenities/marina.jpg",
 "Indian Cove Marina, a 110-slip working marina tucked into a wooded cove.",
 """  <section class="article"><div class="wrap"><div class="split">
    <div class="prose">
      <h2>Indian Cove Marina</h2>
      <p>The marina is a treasured amenity of the Pointe, set in a sheltered cove on the community's west side.</p>
      <h3>Temporary moorage</h3>
      <p>Only property owners should contact the Harbormaster. To request temporary moorage, email the Harbormaster with the dates needed, the beam and length of the boat, and the property address to be billed, or use the amenity booking service in the <a href="https://app.condocontrol.com/login" target="_blank" rel="noopener">Owner Portal</a>.</p>
      <p>Temporary moorage is limited to property owners and their guests. Property owners must be on-site during the requested moorage dates for a guest. Moorage is not available to renters. Required paperwork is in the mailbox near the pavilion. Every effort is made to accommodate all boats, please contact the Harbormaster if you need to cancel, to avoid being billed.</p>
      <h3>Marina information</h3>
      <ul>
        <li>100+ slips from 20&ndash;55 feet in length; slips are fully leased.</li>
        <li>Transient moorage for owners and their guests at $1.00 per foot/day.</li>
        <li>Slips are leased long-term by owners, who may sublet or sell only to other property owners.</li>
        <li>Seven security cameras are installed, four with infrared capability.</li>
      </ul>
      <h3>Kayak &amp; canoe storage</h3>
      <p>Racks are available at the marina and other locations for storing kayaks and canoes for an annual fee. Check with the HPMA office regarding fees and availability.</p>
      <h3>Boat ramps</h3>
      <p>There are two boat ramps, off Chesapeake Drive and in the North Beach Lagoon. These are not part of Indian Cove Marina but are maintained by HPMA. Consider the tide charts when using both ramps, especially in the lagoon.</p>
      <h2>A little history</h2>
      <p>When Quadrant developed Hartstene Pointe in the 1970s, many buyers believed they were promised a marina. A settlement led to a 20-slip marina. Years later, 100 property owners funded ($400,000) the current 110-slip marina. Under the agreement with HPMA, leaseholders maintain the marina's operation at no cost to HPMA, and the annual moorage assessments support maintenance, insurance, office assistance, the Harbormaster and the Washington State shoreline lease, with residual funds set aside for future dredging and major repairs.</p>
    </div>
    <aside class="aside">
      <h4>Harbormaster</h4>
      <div class="info-row"><b>Tammy Thomas</b><span>(360) 229-3137</span></div>
      <div class="info-row"><b>Email</b><span><a href="mailto:harbormaster@hpma.org">harbormaster@hpma.org</a></span></div>
      <h4 style="margin-top:20px">Reference</h4>
      <ul>
        <li><a href="../assets/docs/moorage-rules.pdf" target="_blank" rel="noopener">Moorage Rules &amp; Handbook</a></li>
        <li><a href="../assets/docs/moorage-agreement.pdf" target="_blank" rel="noopener">Moorage Agreement &amp; Declaration</a></li>
      </ul>
      <p style="margin-top:14px"><a class="btn" href="https://app.condocontrol.com/login" target="_blank" rel="noopener">Owner Portal &#8599;</a></p>
    </aside>
  </div></div></section>""")

amenity("boat-rv-storage.html","Boat &amp; RV Storage","Boat &amp; RV Storage","assets/img/amenities/marina.jpg",
 "On-site storage for boats, trailers, RVs, kayaks and canoes, available to all owners.",
 """  <section class="article"><div class="wrap"><div class="prose">
    <p>HPMA provides on-site storage areas for boats and trailers, RVs, utility trailers, kayaks and canoes for a fee. These amenities are available to all owners. In addition, the community has two boat launches.</p>
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
      <p>Enjoy our Fitness Center, located across the road from the Clubhouse in the Maintenance Facility Building. It is open 24 hours a day; a gate card is required for entry.</p>
      <h3>Facility rules</h3>
      <ul>
        <li>Clean equipment <strong>before and after</strong> each use (cleansers and sanitizers are provided).</li>
        <li>Sign in on the clipboard provided; normal Fitness Center rules apply.</li>
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
    </div>
    <aside class="aside">
      <h4>Equipment manuals</h4>
      <ul>
        <li><a href="../assets/docs/elliptical-trainer-manual.pdf" target="_blank" rel="noopener">Elliptical trainer manual</a></li>
        <li><a href="../assets/docs/indoor-cycle-manual.pdf" target="_blank" rel="noopener">Indoor cycle manual</a></li>
      </ul>
      <h4 style="margin-top:20px">Recreation Committee</h4>
      <p>Contact the <a href="../contact/">office</a> to get involved.</p>
    </aside>
  </div></div></section>""")

amenity("outdoor-recreation.html","Outdoor Recreation","Outdoor Recreation","assets/img/amenities/recreation.jpg",
 "Beyond the beaches, there are outdoor facilities for all ages to enjoy.",
 """  <section class="article"><div class="wrap"><div class="prose">
    <p>In addition to the beautiful beaches that surround the Pointe, there are outdoor recreational facilities for all ages to enjoy. Here is a snapshot of just a few:</p>
    <ul>
      <li><strong>Tennis courts</strong>, two near the Clubhouse, one by the spit</li>
      <li><strong>Basketball &amp; pickleball court</strong>, near the Clubhouse</li>
      <li><strong>Fire pits</strong>, at the Spit</li>
      <li><strong>Playground equipment</strong>, North Beach and the Clubhouse area</li>
      <li><strong>Horseshoes</strong>, North Beach</li>
      <li><strong>Hiking</strong>, about 5.5 miles of community <a href="trails.html">trails</a></li>
    </ul>
    <figure><img src="../assets/img/amenities/recreation.jpg" alt="Tennis courts at Hartstene Pointe"></figure>
  </div></div></section>""")

amenity("picnic-shelters.html","Picnic Shelters","Picnic Shelters","assets/img/amenities/picnic.jpg",
 "Facilities for picnics, gatherings, or just a spot to relax and enjoy nature.",
 """  <section class="article"><div class="wrap"><div class="prose">
    <p>Enjoy our many facilities for picnics, gatherings, or just a spot to relax. Reservations for Hartstene Pointe facilities can be made on a non-exclusive basis. To find an open date, check the calendar of events, complete a <a href="../assets/docs/facilities-use-application.pdf" target="_blank" rel="noopener">Facilities Use Application</a>, and submit it to the HPMA office.</p>
    <h2>North Beach</h2>
    <p>Our largest picnic area, with a covered fireplace, running water, propane barbeque, sink, stovetop, electrical outlet and picnic tables. Horseshoe pits, swings and restrooms are nearby.</p>
    <h2>Clubhouse Gazebo</h2>
    <p>A covered fireplace, electrical outlets, picnic tables and an overhead light, with the playground and pool just steps away.</p>
    <h2>Indian Cove (West Beach / Marina)</h2>
    <p>Steps from the marina docks, with a sink, stovetop, picnic tables, electrical outlets, string lights in the rafters and an outdoor fireplace.</p>
    <h2>Cuttysark Estuary (South Beach)</h2>
    <p>A single picnic table, with a restroom nearby.</p>
    <h2>The Spit</h2>
    <p>Next to the tennis courts, small and intimate, with running water, stovetop, propane barbeque, electrical outlet, covered fireplace and picnic tables.</p>
    <div class="callout"><p>Reserve a facility with the <a href="../assets/docs/facilities-use-application.pdf" target="_blank" rel="noopener">Facilities Use Application</a>, submitted to the <a href="../contact/">office</a>.</p></div>
  </div></div></section>""")

amenity("trails.html","Trails","Trails","assets/img/amenities/trails.jpg",
 "About 5.5 miles of marked trails through the major ravines and along the east and west banks.",
 """  <section class="article"><div class="wrap"><div class="split">
    <div class="prose">
      <p>Enjoy our trails, through the major ravines and along the east and west banks. Trail maps are available at the office for $3.00, and the trails are clearly marked with signage.</p>
      <h3>Rules &amp; considerations</h3>
      <ul>
        <li>Bank erosion is an ongoing problem. Guard rails alert you to dangerous areas, please stay on the trail.</li>
        <li>Expect roots and loose rocks; bring water and, ideally, a companion on all hikes.</li>
        <li>Mountain bikes are prohibited on our trails.</li>
        <li>Dogs must be leashed on the trails.</li>
        <li>No motor vehicle, bicycle or other self-propelled vehicle may be operated on any trail within Hartstene Pointe (per Article VI, Traffic Control, Section 5). A fine is associated with this violation.</li>
      </ul>
      <p>It is your responsibility as a community member to inform your family and guests of these rules.</p>

      <h2>Featured trails</h2>
      <h3>West Bluff &amp; Nature Trail</h3>
      <p>More ups and downs than the east side, a walking stick may help on the steeper hills. On clear days there are views of the Olympic Mountains. Known as the Nature Trail, signs along the way describe the trees and vegetation common at the Pointe, a project of resident and biologist Jim Cary.</p>
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
        <li><a href="../assets/docs/map-1.pdf" target="_blank" rel="noopener">Hartstene Pointe Map 1</a></li>
        <li><a href="../assets/docs/map-2.pdf" target="_blank" rel="noopener">Hartstene Pointe Map 2</a></li>
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
    <p>In 2006, several property owners had a vision to start a pea patch garden. They thought the horseshoe pit behind the tennis court near the Clubhouse would be sunny and was partially fenced.</p>
    <p>The horseshoe pit was relocated to North Beach, fitting for a picnic area, and several owners held pancake breakfasts to raise funds for new fencing. About half the funds were raised that first spring; the remainder came from a $50 first-time fee and a yearly $25 fee, paying for the cedar-plank plot borders and the soil.</p>
    <figure><img src="../assets/img/amenities/pea-patch.jpg" alt="The Pea Patch community garden"></figure>
    <div class="callout"><h4>Pea Patch questions</h4><p>Email <a href="mailto:office@hpma.org">office@hpma.org</a>. The Pea Patch Committee maintains the garden and its charter and plot agreement.</p></div>
  </div></div></section>""")

amenity("wildlife.html","Wildlife","Wildlife &amp; Habitat","assets/img/amenities/wildlife.jpg",
 "Deer, eagles, raccoons and wildflowers, and how to share the Pointe safely.",
 """  <section class="article"><div class="wrap"><div class="prose">
    <div class="callout warn"><h4>Cougar awareness</h4><p>Cougars have been sighted on Pointe trails. Please be aware and keep your family safe: don't leave small children unattended and be sure they are indoors by dusk; don't feed wildlife or feral cats; close off spaces under porches and decks; feed pets indoors; keep dogs and cats in from dusk to dawn; and use garbage cans with tight-fitting lids. Predators follow prey.</p></div>

    <h2>Please do not feed the wildlife</h2>
    <p>Feeding wildlife foods not found in their natural habitat can do more harm than good. Corn, apples and artificial feeds can disrupt an animal's gut microbes, which can lead to starvation when they can't absorb essential nutrients.</p>

    <h2>Raccoons &amp; health</h2>
    <p>Raccoons in the United States are known to carry infectious diseases that can be transmitted to humans and animals through contact with the animals or their waste. People should not handle raccoons or their waste without protection and appropriate training. Anyone who has handled a raccoon, or been bitten, scratched or exposed to their waste, should consult a physician immediately.</p>

    <h2>The Pointe's wildflowers</h2>
    <p>The greenbelt does not feature an abundance of flowers, probably due to deer browsing, but we do have some:</p>
    <ul>
      <li><strong>Twinflower</strong>, moist shady areas, tiny flowers close to the ground; blooms all summer.</li>
      <li><strong>Orange &amp; hairy honeysuckle</strong>, vines among trailside brush; prefers partial shade; blooms late spring to early summer.</li>
      <li><strong>Red Indian paintbrush</strong>, dry environments, high on the bluffs north of the Bo'sun stairs in summer.</li>
      <li><strong>Columbia tiger lily</strong>, shady, moist places, May to August; a spectacular flower, please leave it for the next person to enjoy.</li>
      <li><strong>Yellow violets</strong>, very low-growing, along shady moist trails in spring and early summer.</li>
    </ul>
  </div></div></section>""")

# ============ COMMUNITY ============
page("community/index.html", "Community", "Community",
     [home_link(), "Community"],
     lede="A place to be part of something, or simply to be by yourself and enjoy the natural world.",
     body="""  <section class="article"><div class="wrap"><div class="prose">
    <p>Hartstene Pointe is a community, but also a place where people can be by themselves and enjoy the natural environment. No one is pressured to engage in community activities, but at the same time, the community welcomes people to join together to participate in activities and governance. It's your choice.</p>

    <h2>Take part in governance</h2>
    <p>Many people at the Pointe volunteer to join the Board of Directors, Board committees or ad-hoc committees, or simply lend their voice to governance issues. We encourage owners to do this, we are all owners and stewards of the Pointe, with a responsibility to contribute our thoughts and work for the betterment of our community. Learn more on the <a href="../governance/">Governance</a> and <a href="../governance/committees.html">Committees</a> pages.</p>

    <h2>Activities at the Pointe</h2>
    <p>Most activities are initiated and organized by volunteers or ad-hoc groups. Participating in social and recreational activities is an excellent way to connect with your neighbors, no pressure, no expectations, just do what is comfortable for you.</p>
    <div class="grid-2">
      <div class="callout"><h4>Recurring gatherings</h4><p>Book clubs &middot; Library group &middot; Walking groups &middot; News &amp; Views &middot; Pot-luck dinners &middot; Travel club &middot; Yoga &middot; Music circle</p></div>
      <div class="callout"><h4>Occasional events</h4><p>Holiday celebrations &amp; the 4th of July &middot; Fishing derby &middot; Marina salmon roast &middot; Garage sales &middot; Art exhibits &amp; fairs &middot; Concerts at North Beach</p></div>
    </div>
    <p style="margin-top:24px">See the community in pictures on our <a href="../photos/">Photos</a> page.</p>
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
        <div class="line"><b>Hours</b><span>Mon&ndash;Fri 8:30am&ndash;5:00pm<br>Saturday 10:00am&ndash;Noon</span></div>
      </div>
      <div class="contact-card">
        <h3>Marina &amp; other contacts</h3>
        <div class="line"><b>Harbormaster</b><span>Tammy Thomas<br><a href="tel:+13602293137">(360) 229-3137</a><br><a href="mailto:harbormaster@hpma.org">harbormaster@hpma.org</a></span></div>
        <div class="line"><b>Water &amp; Sewer</b><span>Hartstene Pointe Water-Sewer District<br><a href="tel:+13604272413">(360) 427-2413</a> &middot; <a href="mailto:acct@hpwsd.org">acct@hpwsd.org</a><br><a href="https://www.hpwsd.org/" target="_blank" rel="noopener">hpwsd.org &#8599;</a></span></div>
        <div class="line"><b>Owner Portal</b><span>Pay dues &amp; manage your account<br><a href="https://app.condocontrol.com/login" target="_blank" rel="noopener">Sign in to Condo Control &#8599;</a></span></div>
      </div>
    </div>
    <div class="callout" style="margin-top:30px"><p>The Water-Sewer District is a separate government entity and is not run by Hartstene Pointe. For water and sewer service or billing questions, please contact the District directly.</p></div>
  </div></section>""")

# ============ PHOTO GALLERY ============
GAL = os.path.join(ROOT, "assets", "img", "gallery")
imgs = sorted(os.listdir(GAL), key=str.lower)
items = "".join(
 f'    <a href="../assets/img/gallery/{html.escape(i)}"><img loading="lazy" src="../assets/img/gallery/{html.escape(i)}" alt="Hartstene Pointe"></a>\n'
 for i in imgs)
page("photos/index.html", "Photos", "Photos",
     [home_link(), "Photos"],
     lede=f"Scenes from around the Pointe, sunsets, shoreline, the marina, wildlife and community life, contributed by residents over the years. Click any photo to view it larger.",
     body=f'  <section class="article"><div class="wrap"><div class="gallery">\n{items}  </div></div></section>')

print("ALL PAGES DONE")

