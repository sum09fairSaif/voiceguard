import pytest

torch = pytest.importorskip("torch")  # CI doesn't install it (see requirements-model.txt)
transformers = pytest.importorskip("transformers")

import audio
import score_baseline
from models.ssl_aasist import SslAasist, is_ssl_checkpoint
from score_baseline import MODEL_CONFIG


def tiny():
    """An untrained wav2vec 2.0 with XLS-R's layout but tiny, so tests run in
    seconds without downloading the real 1.2 GB model."""
    return transformers.Wav2Vec2Config(
        hidden_size=32, num_hidden_layers=2, num_attention_heads=2, intermediate_size=64,
        conv_dim=(16,) * 7, num_conv_pos_embeddings=16, num_conv_pos_embedding_groups=4,
        do_stable_layer_norm=True, feat_extract_norm="layer",
    )


@pytest.fixture
def model():
    torch.manual_seed(0)
    return SslAasist(MODEL_CONFIG, tiny())


def test_four_seconds_in_gives_a_real_and_a_fake_score(model):
    x = 0.1 * torch.randn(3, audio.CROP_SAMPLES)

    hidden, logits = model.eval()(x)

    assert logits.shape == (3, 2)
    assert hidden.shape[0] == 3
    assert torch.isfinite(logits).all()


def test_training_reaches_the_front_end_but_not_its_frozen_feature_encoder(model):
    x = 0.1 * torch.randn(2, audio.CROP_SAMPLES)

    model.train()(x, Freq_aug=True)[1].sum().backward()

    assert model.ssl.encoder.layers[0].attention.q_proj.weight.grad is not None
    assert model.project.weight.grad is not None
    assert all(p.grad is None for p in model.ssl.feature_extractor.parameters())


def test_the_two_learning_rate_groups_split_the_parameters_cleanly(model):
    ssl = {id(p) for p in model.ssl_parameters()}
    backend = {id(p) for p in model.backend_parameters()}

    assert ssl and backend and not ssl & backend
    assert ssl | backend == {id(p) for p in model.parameters()}


def test_a_clip_s_loudness_doesnt_change_its_score(model):
    x = 0.1 * torch.randn(1, audio.CROP_SAMPLES)
    model.eval()

    assert torch.allclose(model(x)[1], model(5 * x)[1], atol=1e-4)


def test_scoring_loads_a_fine_tuned_checkpoint_without_the_pretrained_download(model, tmp_path, monkeypatch):
    weights = tmp_path / "xlsr.pth"
    torch.save(model.state_dict(), weights)
    monkeypatch.setattr(transformers.Wav2Vec2Config, "from_pretrained", classmethod(lambda cls, name: tiny()))
    x = 0.1 * torch.randn(2, audio.CROP_SAMPLES)

    loaded = score_baseline.load_model(weights)

    assert is_ssl_checkpoint(torch.load(weights, weights_only=True))
    assert torch.allclose(loaded(x)[1], model.eval()(x)[1], atol=1e-5)


def test_scoring_still_loads_plain_aasist(tmp_path):
    from models.aasist import Model

    weights = tmp_path / "aasist.pth"
    torch.save(Model(MODEL_CONFIG).state_dict(), weights)

    assert type(score_baseline.load_model(weights)) is Model
