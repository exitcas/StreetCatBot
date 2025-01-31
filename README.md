# StreetCatBot
A cat Mastodon bot.

## Install
### Prerequisites
- Python 3
### Process
1. Install required packages using PIP:
    `pip install -r requirements.txt`
2. Download cat face detection model from [here](https://github.com/opencv/opencv/blob/4.x/data/haarcascades/haarcascade_frontalcatface_extended.xml).
3. Edit settings in `.env.example` and rename it in `.env`. You'll need an account in an instance, create an app and save its access token. You'll find it on your developer settings.
4. Run with `python main.py`.