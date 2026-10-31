"""The same claims, written four different ways. Facts and expected outcomes are unchanged.

Styles
    formal    a formal letter
    casual    short, lowercase, typos, abbreviations, policy number only in the subject
    rambling  long, off-topic details, the key facts buried, relative dates ("yesterday")
    formats   numbers and dates in other formats (2.400 €, 14/10/2026, "two glasses of wine")

Relative dates are always computable from the email date (the date the email was received).
The attachments are the same as in the original claim.
"""

PARAPHRASES = {
    # settle: at fault, young driver, assessor (email received 2026-10-15)
    "CLM-B": {
        "formal": """Dear Sir or Madam,

I hereby wish to declare a collision that occurred on 14 October 2026 on the ring road. While changing lanes, I misjudged the distance and struck the vehicle travelling beside me. I accept full responsibility for this accident. The other driver, Ms. Laurent, and I completed and signed a joint accident report.

The repair estimate provided by the garage amounts to €2,400.

Please find enclosed the photographs, the repair quote and the signed accident report.

Yours faithfully,
Lucas Bernard
Policy VER-1002""",
        "casual": """hi,

had a crash yesterday on the ring road, my bad, i changed lanes and didnt see the car next to me. the other driver (ms laurent) and me did the accident report togther, both signed.
garage says 2400 euros for the repairs.
pics + quote + report attached

thx
lucas""",
        "rambling": """Hello,

So, yesterday was one of those days. I was driving back from my sister's place, it was raining a bit and the radio was talking about the football results, and traffic on the ring road was heavy as usual on a Wednesday. Long story short, when I changed lanes I misjudged the distance and hit the car next to me, which was entirely my fault, I won't pretend otherwise. Luckily nobody was hurt. The other driver, a Ms. Laurent, was very calm about it and we filled in and signed the accident report right there. My car is a Renault Clio, it's quite new, I only got my licence two years ago, so I was quite upset. Anyway, I took it to the garage this morning and they quoted two thousand four hundred euros to fix it.

I attached the photos, the quote and the accident report.

Best,
Lucas Bernard (policy VER-1002)""",
        "formats": """Hello Veridia,

Date of accident: 14/10/2026.
What happened: lane change on the ring road, I misjudged the gap and hit the neighbouring car. Fault: mine (100%).
Other party: Ms. Laurent, accident report signed by both of us.
Repair quote: 2.400,00 € (incl. VAT).

Regards,
L. Bernard, policy no. VER-1002""",
    },
    # settle: not at fault, waiver (email received 2026-10-14)
    "CLM-A": {
        "formal": """Dear Veridia claims department,

I am writing to report an accident which took place on 12 October 2026 at the Rue de Rivoli crossing. A van failed to stop at a red light and collided with the side of my vehicle. The van driver, Mr. Dubois, acknowledged that he was responsible, and we both signed the accident report.

The garage has quoted €1,200 for the repairs. The photographs, the quote and the signed report are attached.

Yours sincerely,
Claire Martin
Policy number: VER-1001""",
        "casual": """hello

a van went through a red light on monday and hit my car at rue de rivoli. the driver mr dubois said it was his fault, we both signed the report.
quote from the garage = 1200€
attaching photos, quote, report

claire""",
        "rambling": """Hi there,

I hope you're well. I've been meaning to write since the day before yesterday, but work has been crazy. I was on my way to a meeting near the Louvre, running a bit late as always, and as I crossed at the Rue de Rivoli a van just ran the red light and smashed into the side of my car. Can you believe it? The driver, a Mr. Dubois, was apologetic and admitted straight away it was his fault, and we both signed the accident report. I had to cancel my meeting, which was annoying. The garage looked at it and quoted one thousand two hundred euros.

Photos, quote and report attached.

Thanks,
Claire Martin, VER-1001""",
        "formats": """Accident on 12.10.2026, Rue de Rivoli crossing.
Third party: van driver Mr. Dubois, ran the red light, admitted fault, joint report signed.
Me: not at fault.
Repair estimate: EUR 1.200.

Claire Martin / VER-1001""",
    },
    # settle: theft (email received 2026-10-12)
    "CLM-09": {
        "formal": """Dear Sir or Madam,

I regret to inform you that my vehicle was stolen from a public car park during the night of 11 October 2026. I filed a complaint at the police station this morning; the police report is attached.

Yours faithfully,
Emma Rousseau
Policy number: VER-1007""",
        "casual": """hi
my car got stolen last nite from a public parking :( went to the police this morning, report attached
emma""",
        "rambling": """Hello,

I can't quite believe I'm writing this. Last night I went to the cinema with a friend, we saw a long French drama, and I parked in the public car park next to it, like I always do. When we came out around eleven my Tesla was simply gone. I walked around three times thinking I had forgotten where I parked. Then I realised it had been stolen. This morning I went to the police station and filed a complaint. The police report is attached.

Emma Rousseau
(policy VER-1007)""",
        "formats": """Theft of vehicle, night of 11/10/2026, public car park.
Police complaint filed 12/10/2026 (report attached).
Policyholder: E. Rousseau, policy VER-1007.""",
    },
    # request documents: photos missing (email received 2026-10-19)
    "CLM-12": {
        "formal": """Dear Sir or Madam,

On 18 October 2026, while parking, I scraped my vehicle against a low wall. No other party was involved. Unfortunately, I did not take any photographs of the damage. The garage's repair quote of €700 is attached.

Yours faithfully,
Thomas Petit
Policy number: VER-1004""",
        "casual": """hey
scraped a low wall yesterday when parking, nobody else involved. no pics sorry forgot. garage quote 700 eur attached
tom""",
        "rambling": """Good morning,

Yesterday was Sunday and I went to the market as usual. The parking there is really tight, there's this low wall at the entrance, and while I was manoeuvring I scraped the side of my Golf against it. Nobody else was involved, it was just me being clumsy. I was so annoyed that I completely forgot to take pictures. The garage had a look this morning and the quote is seven hundred euros, it's attached.

Thomas Petit, VER-1004""",
        "formats": """Incident 18/10/2026: scraped a low wall while parking. No third party.
Photos: none taken.
Quote: 700,00 €, attached.
T. Petit, policy VER-1004""",
    },
    # escalate: possible alcohol exclusion (email received 2026-10-22)
    "CLM-16": {
        "formal": """Dear Sir or Madam,

I wish to report an accident that occurred on 21 October 2026. On my way home from a friend's birthday celebration, at which I had consumed some alcohol, I lost control of my vehicle and struck a fence. No other party was involved.

The repair quote amounts to €1,800. Photographs and the quote are attached.

Yours faithfully,
Thomas Petit
Policy number: VER-1004""",
        "casual": """hi
last nite after my mates bday party (had a couple of beers) i lost control and hit a fence. no one else involved. garage quote 1800€. pics and quote attached
tom""",
        "rambling": """Hello,

Yesterday evening was my best friend's 40th birthday, a big party at his house with music and a huge cake. I stayed until late, we had a great time and I'd been drinking a bit like everyone, and on the way home on a dark country road I lost control of the car and went into a fence. No one else was involved, thankfully. The garage says one thousand eight hundred euros to repair it. Photos and quote attached.

Thomas Petit (VER-1004)""",
        "formats": """Accident: 21/10/2026, evening, single vehicle (hit a fence), no third party.
Context: returning from a birthday party, I had two glasses of wine.
Quote: EUR 1.800.
T. Petit, VER-1004""",
    },
    # escalate: late report, 9 days (email received 2026-10-11)
    "CLM-15": {
        "formal": """Dear Sir or Madam,

I would like to report an incident that occurred on 2 October 2026, when I struck a bollard while parking. No other party was involved. Please accept my apologies for the delay in reporting it; I was very busy at work.

The repair quote amounts to €650. Photographs and the quote are attached.

Yours faithfully,
Claire Martin
Policy number: VER-1001""",
        "casual": """hi, sorry for writing so late, i hit a bollard parking on friday the 2nd. just me. work was crazy. quote is 650e, pics + quote attached. claire""",
        "rambling": """Hello,

I'm sorry it took me so long. Nine days ago, I was parking near my office and I hit a bollard I hadn't seen, nobody else was involved. Then I had a huge project deadline, my manager was away, and I simply didn't have a minute to deal with it. I finally went to the garage and they quoted six hundred and fifty euros. Photos and quote attached.

Claire Martin, VER-1001""",
        "formats": """Date of incident: 02/10/2026 (bollard, while parking, no third party).
Reported today. Sorry for the delay (work).
Repair quote: 650,00 €.
C. Martin, VER-1001""",
    },
}
