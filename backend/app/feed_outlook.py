"""Read-only cycle forecast derived from the current approved ration and farm records."""
import json
from collections import defaultdict
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select

from .feeding import (FEEDING_PROFILE_VERSION, FarmFeedingProfileApproval, FeedProduct, FeedingRecommendation, RecommendationIn, evaluate_ration,
                      evaluate_saved_ration, recommendation_view, species_key, stock, now)
from .feeding_sessions import operational_schedule
from .main import CurrentUser, Db, ProductionUnit, app, owned_farm
from .operations import StockingCycle


def day_sessions(db, cycle_id, day, ration, default_count):
    schedule = operational_schedule(db, cycle_id, day)
    windows = list(json.loads(schedule.windows_json).values()) if schedule else [{} for _ in range(default_count)]
    return [
        {'number': i, 'name': window.get('name'), 'start': window.get('start'), 'end': window.get('end'),
         'quantity_kg': round(ration * (window.get('allocation_pct') or 100 / len(windows)) / 100, 6)}
        for i, window in enumerate(windows, 1)
    ]


@app.get('/farms/{farm_id}/feed-outlook', tags=['Feeding and inventory'])
def feed_outlook(farm_id: int, user: CurrentUser, db: Db):
    farm = owned_farm(farm_id, user, db)
    today = now().date()
    dates = [today + timedelta(days=offset) for offset in range(1, 8)]
    products = {feed.id: feed for feed in db.scalars(select(FeedProduct).where(FeedProduct.farm_id == farm_id))}
    cycles = db.execute(select(StockingCycle, ProductionUnit).join(
        ProductionUnit, ProductionUnit.id == StockingCycle.unit_id,
    ).where(ProductionUnit.farm_id == farm_id, ProductionUnit.is_active.is_(True),
            StockingCycle.closed_at.is_(None)).order_by(ProductionUnit.name, StockingCycle.id)).all()
    latest = {}
    for recommendation in db.scalars(select(FeedingRecommendation).where(
        FeedingRecommendation.farm_id == farm_id,
        FeedingRecommendation.cycle_id.in_([cycle.id for cycle, _ in cycles]),
    ).order_by(FeedingRecommendation.created_at.desc(), FeedingRecommendation.id.desc())):
        latest.setdefault(recommendation.cycle_id, recommendation)

    confirmed_species = set(db.scalars(select(FarmFeedingProfileApproval.species).where(
        FarmFeedingProfileApproval.farm_id == farm_id,
        FarmFeedingProfileApproval.profile_version == FEEDING_PROFILE_VERSION,
        FarmFeedingProfileApproval.active.is_(True),
    )))
    results = []
    demand = defaultdict(float)
    for cycle, unit in cycles:
        item = latest.get(cycle.id)
        status = item.status if item else 'draft'
        review = recommendation_view(item) if item else None
        feed = products.get(item.feed_id) if item else None
        reasons = []
        current = None
        try:
            current = (evaluate_saved_ration(farm_id, cycle, item, db) if item else evaluate_ration(
                farm_id, cycle, None, RecommendationIn(feed_id=1), db, require_confirmation=False))
        except HTTPException as error:
            reasons.append(str(error.detail))
            if status in ('approved','pending_approval'):
                status = 'expired'
        if current:
            reasons.extend(current['warnings'][2:])
            if item and current['status'] != 'pending_approval':
                status = current['status']
            if item and current['status'] == 'pending_approval':
                original_profile = review['inputs'].get('profile', {})
                if (original_profile.get('maximum_weight_g') != current['profile']['maximum_weight_g']
                    or item.profile_version != current['profile']['version']
                    or item.profile_approval_id != current['approval'].id):
                    status = 'expired'
                    reasons.append('Review the current species and weight profile and calculate a fresh recommendation.')
                elif item.status == 'pending_approval' and (
                    item.sampling_id != current['snapshot']['sampling_id'] or item.water_quality_id != current['snapshot']['water_quality_id']
                    or item.estimated_live_count != current['snapshot']['estimated_population']
                ):
                    status = 'expired'
                    reasons.append('Farm records changed. Calculate and review a fresh recommendation.')
        if not item:
            reasons.append('Select a feed product and calculate a recommendation.' if products else 'Add a feed product in Feed Inventory.')
        elif status == 'pending_approval':
            reasons.append('Recommendation awaiting approval.')
        elif status != 'approved' and not reasons:
            reasons.append('Calculate and review a fresh recommendation.')
        daily = []
        if status == 'approved' and current and feed:
            ration = current['daily_ration']
            for day in dates:
                daily.append({'date': day, 'daily_kg': ration,
                              'sessions': day_sessions(db, cycle.id, day, ration, item.session_count)})
            demand[feed.id] += sum(row['daily_kg'] for row in daily)
        snapshot = current['snapshot'] if current else {}
        results.append({
            'unit_id': unit.id, 'unit_name': unit.name, 'unit_type': unit.unit_type, 'cycle_id': cycle.id, 'species': cycle.species,
            'status': status, 'reasons': list(dict.fromkeys(reasons)), 'recommendation': review,
            'profile_species': species_key(cycle.species), 'profile_confirmed': species_key(cycle.species) in confirmed_species,
            'feed_id': feed.id if feed else None, 'feed_name': feed.name if feed else None,
            'estimated_live_count': snapshot.get('estimated_population'), 'average_weight_g': snapshot.get('average_weight_g'),
            'biomass_kg': current['biomass_kg'] if current else None, 'feeding_rate_pct': item.daily_rate_pct if item else None,
            'sampled_on': snapshot.get('sampled_on'), 'water_observed_at': snapshot.get('water_observed_at'),
            'forecast': daily, 'forecast_kg': round(sum(row['daily_kg'] for row in daily), 6) if daily else None,
        })
    inventory = []
    for feed in products.values():
        available = stock(feed.id, db)
        needed = round(demand[feed.id], 6)
        inventory.append({'feed_id': feed.id, 'name': feed.name, 'available_kg': available,
                          'required_kg': needed, 'remaining_kg': round(available-needed, 6),
                          'shortage_kg': round(max(0, needed-available), 6),
                          'coverage_days': round(7 * max(0, available) / needed, 1) if needed else None})
    return {'farm_name': farm.name, 'timezone': 'Africa/Accra', 'dates': dates, 'cycles': results, 'inventory': inventory}
