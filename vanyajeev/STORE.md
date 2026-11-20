# Publishing Vanyajeev to the Microsoft Store

Registration is free for individual developers, and the Store signs and hosts the app, so no code-signing certificate is needed.

1. **Create a developer account**: go to [storedeveloper.microsoft.com](https://storedeveloper.microsoft.com), choose **Individual developer**, sign in with a personal Microsoft account and verify your ID.
2. **Reserve the name**: in [Partner Center](https://partner.microsoft.com/dashboard) → *Apps and games* → *New product* → *MSIX or PWA app* → reserve **Vanyajeev**.
3. **Copy the identity**: open the app → *Product management* → *Product identity*. Note:
   - `Package/Identity/Name` (e.g. `12345SanjeevMishra.Vanyajeev`)
   - `Package/Identity/Publisher` (e.g. `CN=1A2B3C4D-...`)
   - `Package/Properties/PublisherDisplayName`
4. **Give them to the build**: in GitHub → repo *Settings* → *Secrets and variables* → *Actions* → *Variables*, add:
   - `MSIX_IDENTITY_NAME`
   - `MSIX_PUBLISHER`
   - `MSIX_PUBLISHER_DISPLAY`
5. **Build**: push a tag such as `vanyajeev-v1.0.0` (or run the workflow manually). Download `Vanyajeev-1.0.0.msix` from the release or the run's artifacts.
6. **Submit**: in Partner Center → *Start your submission*:
   - **Pricing**: Free.
   - **Properties**: category *Photo & video*; privacy policy URL (Vanyajeev processes photos only on the device and sends nothing anywhere).
   - **Age rating**: complete the questionnaire.
   - **Packages**: upload the `.msix`.
   - **Store listing**: description, screenshots (at least one, 1366×768 or larger), the icon from `vanyajeev/assets/icon.png`.
   - **Restricted capability**: explain `runFullTrust`: "Desktop photo editor that reads and writes the user's image files."
7. **Submit for certification**: usually a few business days.

Before step 2, search the Store for the name; if "Vanyajeev" is taken, reserve a variant.
