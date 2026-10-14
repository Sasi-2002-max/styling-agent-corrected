# StyleAI luxury home-page patch

This patch recreates the visual direction of the supplied reference: a
full-width luxury fashion hero, warm editorial tones, serif display type,
refined gold accents, and a row of four direct links for Profile, AI Stylist,
Fitting Room, and My Wardrobe. The existing home-page prompt and occasion
selection are retained and still open the AI Stylist with those values.

The hero image is cropped from the fashion storefront visible inside the
user-provided screenshot, excluding the surrounding phone/reel controls. The
source is a photographed 500 × 310 screen capture, so it will be softer than
the original image shown in the video. A clean, high-resolution copy of that
storefront image would improve sharpness without changing the layout.

## Files to copy

- `frontend/src/App.jsx`
- `frontend/src/App.css`
- `frontend/src/pages/home.jsx`
- `frontend/src/pages/Home.css` (new)
- `frontend/src/assets/styleai-aura-home.jpg` (new, cropped from the supplied reference)

Copy each file to the matching path in the project. No backend, API settings,
dependencies, `.env`, or credentials are changed or included.

## Verification

- Confirmed the home prompt still submits its prompt and selected occasion to
  the existing AI Stylist route.
- Confirmed the four requested quick links point to the existing app routes.
- CSS brace checks and asset/archive integrity checks passed.
- A frontend build/browser preview was not available because the project's
  frontend dependencies are not installed in this environment.
