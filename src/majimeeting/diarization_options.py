"""Validated Community-1 controls, independent of Torch and Qt."""
import math
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class DiarizationOptions:
    min_speakers: int = 0
    max_speakers: int = 0
    threshold: float | None = None
    fa: float | None = None
    fb: float | None = None
    min_duration_off: float | None = None
    exclude_overlap: bool | None = None
    segmentation_batch_size: int = 0
    embedding_batch_size: int = 0
    track_speakers: dict = field(default_factory=dict)

    def validate(self, speakers=0):
        validate_counts(speakers, self.min_speakers, self.max_speakers)
        for name, low, high in [('threshold', .5, .8), ('fa', .01, .5),
                                ('fb', .01, 15.), ('min_duration_off', 0., 1.)]:
            value = getattr(self, name)
            if value is not None and (not isinstance(value, (int, float)) or
                                      not math.isfinite(value) or not low <= value <= high):
                raise ValueError(f'Paramètre {name} hors limites [{low}, {high}].')
        if self.exclude_overlap is not None and not isinstance(self.exclude_overlap, bool):
            raise ValueError('Exclusion des chevauchements invalide.')
        for value in (self.segmentation_batch_size, self.embedding_batch_size):
            if type(value) is not int or not 0 <= value <= 64:
                raise ValueError('Lots de diarisation : 0 (modèle) à 64.')
        for track, counts in self.track_speakers.items():
            if not track.startswith('track-') or '/' in track or '\\' in track:
                raise ValueError('Piste invalide.')
            validate_counts(counts['speakers'], counts['min_speakers'], counts['max_speakers'])
        return self

    def for_track(self, track, speakers):
        values = asdict(self)
        values.pop('track_speakers')
        values['speakers'] = speakers
        values.update(self.track_speakers.get(track, {}))
        return values


def validate_counts(exact, minimum, maximum):
    if any(type(v) is not int or not 0 <= v <= 50 for v in (exact, minimum, maximum)):
        raise ValueError('Nombre de voix : entier entre 0 et 50.')
    if exact and (minimum or maximum):
        raise ValueError('Choisissez un nombre exact OU des bornes minimum/maximum.')
    if minimum and maximum and minimum > maximum:
        raise ValueError('Le minimum de voix dépasse le maximum.')


# Executed inside the isolated runtime; no imports from the GUI installation.
RUNTIME_CONFIGURATION = r'''
def configure_pipeline(pipeline, settings):
    parameters = pipeline.parameters(instantiated=True)
    changes = {}
    for source, target in [('threshold', 'threshold'), ('fa', 'Fa'), ('fb', 'Fb')]:
        if settings.get(source) is not None:
            changes[target] = settings[source]
    if changes:
        if getattr(pipeline, 'klustering', None) != 'VBxClustering':
            raise ValueError('Les réglages de regroupement nécessitent Community-1 / VBxClustering.')
        parameters['clustering'].update(changes)
    if settings.get('min_duration_off') is not None:
        parameters['segmentation']['min_duration_off'] = settings['min_duration_off']
    if changes or settings.get('min_duration_off') is not None:
        pipeline.instantiate(parameters)
    if settings.get('exclude_overlap') is not None:
        pipeline.embedding_exclude_overlap = settings['exclude_overlap']
    for name in ['segmentation_batch_size', 'embedding_batch_size']:
        if settings.get(name):
            setattr(pipeline, name, settings[name])
    counts = {}
    if settings.get('speakers'):
        counts['num_speakers'] = settings['speakers']
    else:
        for key in ['min_speakers', 'max_speakers']:
            if settings.get(key):
                counts[key] = settings[key]
    effective = dict(parameters=pipeline.parameters(instantiated=True), counts=counts,
                     exclude_overlap=pipeline.embedding_exclude_overlap,
                     segmentation_batch_size=pipeline.segmentation_batch_size,
                     embedding_batch_size=pipeline.embedding_batch_size)
    return counts, effective
'''
