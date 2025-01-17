from app import db
from datetime import datetime

class Bill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(20), nullable=False)
    bill_type = db.Column(db.String(10), nullable=False)  # GAS, LUCE, or MIX
    file_path = db.Column(db.String(255))
    cost_per_unit = db.Column(db.Float)  # Cost per KW or Cubic Meter
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'phone': self.phone,
            'bill_type': self.bill_type,
            'cost_per_unit': self.cost_per_unit,
            'created_at': self.created_at.isoformat()
        }