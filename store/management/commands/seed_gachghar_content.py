from django.core.management.base import BaseCommand
from django.db import transaction

from store.models import Guide, HomeSection, StaticPage


PAGES = (
    {
        "slug": "about",
        "title": "About GachGhar",
        "body": (
            "GachGhar is for people who find joy in growing plants and bringing nature into everyday spaces. "
            "We want gardening to feel approachable, whether you are caring for your first pot or tending a garden.\n\n"
            "Our aim is to help people create greener homes and spaces with a considered selection of plants and "
            "gardening essentials. Product information and care guidance are provided to help you choose with care.\n\n"
            "We encourage responsible gardening: choose plants suited to your space, care for them thoughtfully, "
            "and make use of resources such as water and growing media with care. We work to make each GachGhar "
            "experience clear, helpful, and centred on customer satisfaction."
        ),
    },
    {
        "slug": "contact",
        "title": "Contact GachGhar",
        "body": (
            "We are here to help with your GachGhar experience. For an existing order, sign in to your account "
            "and visit My Orders to review its details. For product, plant-care, or general questions, use the "
            "verified contact details shown below."
        ),
    },
    {
        "slug": "privacy",
        "title": "Privacy Policy",
        "body": (
            "GachGhar uses information you provide, such as account, contact, delivery, order, review, newsletter, "
            "and gardening-assistant details, to operate the store, respond to requests, and help complete orders. "
            "The information requested depends on the feature you choose to use.\n\n"
            "The website uses session information to support sign-in, shopping carts, security, and other requested "
            "site functions. Payment details are submitted to the selected payment provider; GachGhar receives the "
            "payment status and references needed to manage an order. A provider may process information under its "
            "own terms and privacy notice.\n\n"
            "Access to information is limited to the operational needs of the store. To ask about, correct, or "
            "request deletion of account information, use the verified contact details on the Contact page. Some "
            "records may need to be retained where applicable law or an active transaction requires it. This policy "
            "describes the website's current intended practices and should be reviewed as the service changes."
        ),
    },
    {
        "slug": "terms",
        "title": "Terms and Conditions",
        "body": (
            "These terms describe use of the GachGhar website and store. By using an account or placing an order, "
            "you agree to provide accurate information and use the site lawfully. Contact GachGhar if you find an "
            "error in an order or account detail.\n\n"
            "Product descriptions, images, prices, and availability are shown to help you make a choice. Plants are "
            "living products, so appearance can vary with season and natural growth; check the product information "
            "before ordering. The final payable amount, including any applicable delivery charge or discount, is "
            "shown at checkout before you submit an order.\n\n"
            "Submitting an order is a request to purchase. GachGhar must be able to verify the order and any required "
            "payment before it is processed. A browser message alone does not confirm payment. Shipping, returns, "
            "refunds, and privacy are described on their respective pages. These terms do not limit rights that "
            "cannot be limited under applicable law."
        ),
    },
    {
        "slug": "shipping",
        "title": "Shipping and Delivery Policy",
        "body": (
            "Delivery availability depends on the destination and the products in your cart. Enter a complete and "
            "accurate delivery address and review the delivery charge and any estimate displayed at checkout before "
            "placing an order. GachGhar does not promise a delivery date unless a specific estimate is shown for "
            "your order.\n\n"
            "Keep your order details available so you can review its status from your account. Delivery timing can "
            "depend on the destination, carrier operations, weather, and other circumstances outside the store's "
            "control. If an order appears delayed or has an address problem, contact GachGhar using the verified "
            "details on the Contact page.\n\n"
            "Any delivery charge applicable to an order is shown before the order is submitted. This policy does not "
            "add an unstated fee or delivery-time guarantee."
        ),
    },
    {
        "slug": "returns",
        "title": "Returns and Refund Policy",
        "body": (
            "If an order arrives damaged, incomplete, or different from what was ordered, contact GachGhar as soon "
            "as practical using the verified details on the Contact page. Include the order number and a clear "
            "description of the issue; photographs can help explain a product or transit concern.\n\n"
            "GachGhar will review the order details and the circumstances and explain the available next steps. Any "
            "return, replacement, cancellation, or refund is handled according to the order details and applicable "
            "consumer law. No return window, shipping charge, or refund timeline is promised here unless it is "
            "specifically displayed for the order or confirmed by GachGhar.\n\n"
            "Where a refund is approved, the payment provider or bank may affect when it appears in the customer's "
            "account. This policy does not reduce rights that cannot be limited under applicable law."
        ),
    },
)


GUIDES = (
    ("indoor-plant-care", "How to Care for Indoor Plants", "Match light and watering to each plant's needs.",
     "Start by checking the light in the place where the plant will live. Many foliage plants prefer bright, indirect light; direct sun can be too strong for some varieties.\n\n"
     "Check the growing medium before watering instead of following a fixed calendar. Water thoroughly when the plant needs it, and use a pot with drainage so roots do not sit in water.\n\n"
     "Keep leaves clean, turn the pot occasionally for even growth, and check for pests when watering. Change one care condition at a time so you can see how the plant responds."),
    ("hibiscus-plant-care", "Hibiscus Plant Care", "Give hibiscus suitable light, moisture, and room to grow.",
     "Hibiscus generally grows and flowers best in a bright, sunny position. Introduce a plant to stronger sunlight gradually, especially after moving it from a sheltered nursery.\n\n"
     "Keep the soil evenly moist during active growth, while allowing excess water to drain. Watering frequency changes with temperature, pot size, and weather.\n\n"
     "Remove spent flowers and damaged leaves with clean tools. Watch for common sap-feeding pests and address them early with a plant-safe method."),
    ("rose-plant-care", "Rose Plant Care", "Support healthy roses with light, airflow, and careful watering.",
     "Choose a position with several hours of suitable direct sunlight and enough airflow around the plant. Use a container with drainage or prepare garden soil that does not remain waterlogged.\n\n"
     "Water the soil rather than repeatedly wetting the leaves, and adjust as the weather changes. Feed only according to the product label and the plant's growth stage.\n\n"
     "Remove spent blooms and dead growth with clean pruners. Inspect new growth regularly for pests or leaf spots."),
    ("money-plant-care", "Money Plant Care", "A practical care guide for pothos and other money plants.",
     "Money plants such as pothos grow well in bright, indirect light and can tolerate lower light, though growth may slow. Avoid harsh midday sun on tender leaves.\n\n"
     "Let the top layer of potting mix begin to dry before watering. Drain excess water and use an airy mix so roots are not kept constantly wet.\n\n"
     "Trim long vines to encourage a fuller shape. You can root healthy cuttings in water or a suitable growing medium, and keep the plant away from pets that may chew it."),
    ("snake-plant-care", "Snake Plant Care", "Keep snake plants healthy with bright light and careful watering.",
     "Snake plants tolerate a range of indoor light, from lower light to bright indirect light. Growth is usually stronger with more suitable light, but avoid sudden changes to intense sun.\n\n"
     "Allow the potting mix to dry well between waterings. A free-draining mix and a pot with drainage holes help reduce the risk of root rot.\n\n"
     "Wipe dust from the leaves and remove damaged leaves at the base with clean tools. Water less often in cool or low-light conditions."),
    ("tulsi-plant-care", "Tulsi Plant Care", "Grow Tulsi in a bright spot and respond to its soil and weather.",
     "Tulsi generally prefers a warm, bright location with several hours of sunlight. Protect it from cold conditions and allow good airflow around the foliage.\n\n"
     "Water when the upper growing medium begins to dry, then let excess water drain. Avoid leaving the pot standing in water, especially during cooler weather.\n\n"
     "Pinch growing tips to encourage branching and remove flowers or dry leaves as needed. Check the plant regularly for insects and adjust care to the local season."),
    ("watering-schedules", "How to Build a Watering Schedule", "Use soil checks and plant signals instead of a rigid timetable.",
     "There is no single watering schedule for every plant. Pot size, material, drainage, plant species, light, temperature, and season all affect how quickly soil dries.\n\n"
     "Check the upper soil with a finger or moisture tool. When the plant's needs call for water, water evenly until excess drains, then empty standing water from a saucer.\n\n"
     "Keep brief notes for each plant and adjust after observing it. Yellowing, wilting, or persistently wet soil can have several causes, so check roots, light, and drainage before changing the amount of water."),
    ("soil-preparation", "Preparing Soil for Pots and Garden Beds", "Choose a growing medium that supports roots and drains well.",
     "Different plants need different growing media. For containers, use a mix intended for pots rather than heavy garden soil alone, which can compact and drain poorly in a container.\n\n"
     "Before planting, check that the pot has drainage holes and remove large debris from the mix. Moisten dry media lightly so it holds together without becoming waterlogged.\n\n"
     "Reuse a growing medium only when it is healthy and appropriate for the next plant. Do not reuse material from plants with serious root disease or pest problems."),
    ("organic-compost", "Using Organic Compost in the Garden", "Use mature compost thoughtfully and in suitable amounts.",
     "Well-finished compost is dark, crumbly, and has an earthy smell. Unfinished material can heat up or continue decomposing, so allow it to mature before using it around plants.\n\n"
     "Mix compost into suitable garden soil or apply it as a modest top dressing. For pots, follow the plant's needs and the compost product label; too much compost can hold excess moisture or concentrate nutrients.\n\n"
     "Store compost covered and dry enough to avoid runoff or odour. Wash hands after handling and keep compost away from edible plant parts."),
    ("balcony-gardening", "Getting Started with Balcony Gardening", "Plan a balcony garden around sunlight, space, and safe watering.",
     "Observe the balcony through the day to learn where direct sun falls and how wind moves. Choose plants and containers suited to those conditions rather than buying for appearance alone.\n\n"
     "Check the mature size of each plant and leave room for airflow and care. Use pots with drainage and prevent runoff from affecting neighbours or building surfaces.\n\n"
     "Start with a few manageable plants. Group varieties with similar light and watering needs, then expand as you learn how the balcony changes through the seasons."),
    ("seasonal-gardening-india", "Seasonal Gardening in India", "Adjust plant care as heat, monsoon rain, and cooler weather change.",
     "Across India, local climate and elevation vary widely, so use local weather and each plant's needs as your guide. During hot periods, check containers more often and protect shade-loving plants from harsh afternoon sun.\n\n"
     "During monsoon weather, check drainage and reduce watering when rain keeps the growing medium wet. Move pots out of persistent standing water and watch for fungal problems in crowded, humid spaces.\n\n"
     "In cooler months, growth may slow and soil may dry more slowly. Reduce watering when appropriate, protect sensitive plants from cold nights, and resume pruning or feeding only when active growth returns."),
)


class Command(BaseCommand):
    help = "Prepare original GachGhar pages and gardening guides; preview by default."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Save missing content and publish it.")

    def handle(self, *args, **options):
        if options["apply"]:
            self._seed()
            return
        with transaction.atomic():
            self._seed()
            transaction.set_rollback(True)
        self.stdout.write(self.style.WARNING("DRY RUN ONLY: no content was saved. Use --apply to commit."))

    def _seed(self):
        created_pages = created_guides = 0
        conflicts = []
        for item in PAGES:
            page = StaticPage.objects.filter(slug=item["slug"]).first()
            if page:
                if not page.is_published:
                    conflicts.append(f"Page {page.slug} already exists as an unpublished record; left unchanged")
                    continue
                if page.slug == "about":
                    addition = (
                        "Gardening can begin with one plant. GachGhar aims to make plant care accessible, help "
                        "people create greener homes and spaces, and support thoughtful, responsible gardening. "
                        "We want every customer to have a clear and satisfying experience."
                    )
                    if addition not in page.body:
                        page.body = f"{page.body.rstrip()}\n\n{addition}".strip()
                        page.save(update_fields=("body", "updated_at"))
                continue
            StaticPage.objects.create(**item, is_published=True)
            created_pages += 1

        for slug, title, summary, body in GUIDES:
            guide = Guide.objects.filter(slug=slug).first()
            if guide:
                if not guide.is_published:
                    conflicts.append(f"Guide {guide.slug} already exists as an unpublished record; left unchanged")
                continue
            Guide.objects.create(
                slug=slug,
                title=title,
                summary=summary,
                body=body,
                is_published=True,
            )
            created_guides += 1

        if not HomeSection.objects.filter(kind=HomeSection.Kind.GUIDES).exists():
            HomeSection.objects.create(kind=HomeSection.Kind.GUIDES, title="Garden care guides", sort_order=30)

        self.stdout.write(f"New pages: {created_pages}; new guides: {created_guides}.")
        for conflict in conflicts:
            self.stdout.write(self.style.WARNING(conflict))
