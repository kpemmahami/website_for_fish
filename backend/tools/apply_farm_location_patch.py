"""Run once from backend directory AFTER backing up app/main.py and aquafarm.db."""
from pathlib import Path
p=Path('app/main.py')
s=p.read_text(encoding='utf-8')
if 'farm_address: Mapped[str | None]' in s and 'nearest_landmark: str | None' in s:
    print('Farm location fields already present; no changes made.')
    raise SystemExit(0)
model='    species: Mapped[str] = mapped_column(String(100))\n'
if s.count(model)!=1: raise SystemExit('Unexpected Farm model; stopped without editing.')
s=s.replace(model,model+"""    farm_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    nearest_landmark: Mapped[str | None] = mapped_column(String(200), nullable=True)
""",1)
field='    species: str = Field(min_length=2, max_length=100)\n'
if s.count(field)!=1: raise SystemExit('Unexpected FarmIn model; stopped without editing.')
s=s.replace(field,field+"""    farm_address: str | None = Field(default=None, max_length=500)
    nearest_landmark: str | None = Field(default=None, max_length=200)
""",1)
compile(s,str(p),'exec')
p.write_text(s,encoding='utf-8')
print('Farm model and request/response schemas updated.')
