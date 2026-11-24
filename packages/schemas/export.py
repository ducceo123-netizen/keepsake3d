"""Run `python -m packages.schemas.export` from the repository root."""
import json
from pathlib import Path
from .models import Parameters, DemoManifest, Corrections

for name,model in [('parameters',Parameters),('design-manifest',DemoManifest),('corrections',Corrections)]:
    Path(__file__).with_name(f'{name}.schema.json').write_text(json.dumps(model.model_json_schema(),indent=2)+'\n')
