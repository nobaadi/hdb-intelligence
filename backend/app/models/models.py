from sqlalchemy import Column, Integer, String, Float, Index

from app.db.database import Base


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    month = Column(String(7), nullable=False)
    town = Column(String(60), nullable=False)
    flat_type = Column(String(30), nullable=False)
    block = Column(String(10))
    street_name = Column(String(100))
    storey_range = Column(String(20))
    floor_area_sqm = Column(Float)
    flat_model = Column(String(50))
    lease_commence_date = Column(Integer)
    remaining_lease = Column(String(30))
    resale_price = Column(Float, nullable=False)
    price_per_sqm = Column(Float)

    __table_args__ = (
        Index("ix_month_town", "month", "town"),
        Index("ix_town_flat", "town", "flat_type"),
    )
