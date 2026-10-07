# Substack and Medium, October 2026

Two versions of the same story for the people who already follow you. The Substack
is short and personal, with one ask. The Medium piece is the full article from
`outreach/article.html` with the figures refreshed to the 4 October register
snapshot and the typo fixed. Both go out under your name; nothing here is sent by
the automation.

Numbers verified against the live site on 7 October: median €0.41/kWh, Vattenfall
€0.32, E-Flux €0.51, 79,147 public charge points, 323 garages, Amsterdam street
€8.05/h, Utrecht €5.10/h, naheffing €82. The per-city table in the Medium piece is
the one from the article (two hours of parking at the centre tariff); it was
computed on 30 September and the centre tariffs have not changed since.

---

## Substack

**Subject line:** I built the thing I could not find: what a charging stop really costs

**Preview text:** Two bills, two companies, and nothing that adds them up. So I joined the registers.

**Body:**

Charging an electric car in the Netherlands means paying twice. The electricity goes
through your charge card. The parking under the post goes through the municipality,
on a different app, and nothing at the charge point mentions it.

I wanted a cheap charger with cheap parking. No app answers that. So I took the two
national registers, every public charge point and every official parking tariff, and
joined them.

What the join shows, for an ordinary stop of 20 kWh over two hours:

- The electricity costs about €8.20 at the median of €0.41 per kWh, almost anywhere.
- The parking is what moves. €7.28 in Delft, €7.16 in Utrecht, €3.00 in Eindhoven.
- In Delft and Utrecht, nearly half of the bill is not electricity. Across 14 cities
  the average is 38%.
- The operator matters more than the city. Vattenfall averages €0.32 per kWh,
  E-Flux €0.51, for the same grid, often on the same street.

So I built a map that adds the two up for the stop you set: arrive, leave, how much
energy. Every public charger in the country, 79,147 of them, with the parking under
it. Free, no sign-up, no app, and it does not take money from any operator.

https://parkingnetherlands.com/ev-charging

Since I last wrote: the pin now shows one total instead of a split, a reader
pointed out that an 11 kW post cannot deliver 20 kWh in half an hour so the model
now bills only what the post can deliver, and the whole thing exists in Dutch,
German and French. The data behind it is open under CC BY.

One ask. Try it for a stop you actually make, and reply to this email with the
price it gives you and whether that matched reality. The map is only as good as the
registers, and the registers are wrong in places. The replies are how I find them.

Aakash

---

## Medium

**Title:** You pay twice to charge a car in the Netherlands, and nothing shows you both

**Subtitle:** I joined the national charge point register to the national parking register. Parking turned out to be 38% of a charging stop.

**Tags:** Electric Vehicles, Netherlands, Open Data, Data Analysis, Urban Mobility

**Body:**

Charging an electric car in the Netherlands involves two separate payments, and most
of us only ever think about one of them.

The electricity goes through your charge card. You hold the card against the post,
the kWh are metered, and that bill comes from whoever issued the card.
Straightforward enough.

The parking is the other one. A charging bay inside a paid parking zone is still a
paid parking space. The street tariff runs for the whole time you are plugged in,
you pay it through a completely different app or meter, and nothing at the charge
point mentions it.

Two bills, two companies, no connection between them. Which means when you are
deciding where to go, you can see one number and not the other.

### What I was actually trying to do

I wanted to find a cheap charger with cheap parking. That is the entire question,
and I could not find anywhere that answers it.

There are plenty of apps that show charger prices. There are plenty that handle
parking. I could not find one that puts them together, which seems odd, because the
two costs are completely entangled and you cannot avoid either.

So I went and got the data instead. The national charge point register has every
public post in the country, 79,147 of them. The national parking register has the
tariffs. Both are public. As far as I could tell nobody had joined them, so I did.

### What the join shows

Take an ordinary stop. Twenty kWh over two hours, a top-up while you do something
else rather than a full charge.

The electricity comes to €8.20 at the national median of €0.41 per kWh, and that
figure barely moves around the country. The parking is what changes.

| City | Parking, 2 hrs | Total | Parking's share |
|---|---|---|---|
| Delft | €7.28 | €15.48 | 47% |
| Utrecht | €7.16 | €15.36 | 47% |
| Haarlem | €6.98 | €15.18 | 46% |
| The Hague | €6.40 | €14.60 | 44% |
| Amsterdam | €6.00 | €14.20 | 42% |
| Nijmegen | €5.80 | €14.00 | 41% |
| Zwolle | €5.46 | €13.66 | 40% |
| Groningen | €4.50 | €12.70 | 35% |
| Maastricht | €4.34 | €12.54 | 35% |
| Rotterdam | €4.00 | €12.20 | 33% |
| Breda | €4.00 | €12.20 | 33% |
| Tilburg | €4.00 | €12.20 | 33% |
| Leiden | €3.80 | €12.00 | 32% |
| Eindhoven | €3.00 | €11.20 | 27% |

In Delft and Utrecht nearly half of what a charging stop costs you is not
electricity. Across these fourteen cities the average is 38%.

At least 12,667 Dutch charge points sit inside a paid parking area. Nobody is doing
anything underhand. It is two systems that were built separately and have no
particular reason to talk to each other.

### The variables you cannot see

The electricity is not one price either. The median is €0.41 per kWh, but most
posts land somewhere between €0.28 and €0.63. Same grid, same electricity. The
variable is whose logo is on the post. Vattenfall InCharge averages €0.32, E-Flux by
Road averages €0.51.

Then there is the card. Each charge card negotiates its own rate with each operator,
so the cheapest card is a different card at different posts. At one socket the gap
between the best and worst card commonly runs 40 to 70 percent.

Operator, card, parking. Three things moving at once, none of which you can compare
while standing on a pavement.

### What I built

Every public charge point in the country, what the electricity costs there, and the
parking tariff for the ground underneath it, added together for however long you
actually intend to stay.

It is free, there is no sign-up and no app, and I am not selling anything. I mention
that because it is a fair thing to wonder about.

https://parkingnetherlands.com/ev-charging

Three things I got wrong on the way, because they are the useful part. The register
does not publish occupancy, so the map shows faults and uptime, not whether a bay is
free; it says so on every card. Only 44% of posts publish a tariff, so the rest are
priced with the operator's usual rate or the national median, and labelled. And a
reader pointed out that asking an 11 kW post for 20 kWh in a 30 minute stop is
impossible, so the model now bills only what the post can deliver in the time you
are there.

Even if you never use it, the habit worth having is checking whether the bay sits in
a paid zone before you plug in. It takes seconds and it is the largest avoidable
cost here. Driving to a cheaper city saves you very little; the gap between two
posts on the same street can be much bigger.

*Charging data: the national charge point register via NDW and DOT-NL. Parking
tariffs: the national parking register, 323 register-listed garages across 14
cities, snapshot 4 October 2026. Both datasets are published openly on the site
under CC BY 4.0. The figures above use median tariffs, so an individual stop will
differ; if you find an error in the arithmetic I would like to hear about it.*

---

## Sending

- Substack: new post, paste the body, set the subject and preview text, send to all
  subscribers. Tuesday to Thursday, 08:00 to 10:00 Dutch time gets the best open rate
  for a list this size.
- Medium: new story, paste the body (the table pastes as a table from a Markdown
  preview, not from raw text), add the five tags, publish. Then add the Medium link
  to the Substack footer the next time you write.
- Both: the only link is the charging map. One link per piece is what keeps the
  click-through honest and the referral visible in analytics.
