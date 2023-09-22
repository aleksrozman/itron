[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)
[![hacs][hacsbadge]][hacs]

![Project Maintenance][maintenance-shield]
[![BuyMeCoffee][buymecoffeebadge]][buymecoffee]



HACS integration for municipalities that use itron-hosting.com such as the [City Of Bismarck Public Works](https://bism-p-ia-wb.itron-hosting.com/AnalyticsCustomerPortal_BISM_PROD). Right now it supports the water meter reading on an hourly basis and refreshes daily, in addition to providing some of the statistics like highest usage date and amount which can be used as triggers. It should backfill some of the data. This was inspired by [opower](https://next.home-assistant.io/integrations/opower/), but the underlying API is not a guarantee since it is not a publicly known/documented one. As such, it is mostly an interface into [Itron](https://www.itron.com/) which is a meter utility company. This project is not affiliated with, nor coordinated with, the municipality/company that hosts the data. This is meant to be a convenience for those who might go to their municipality's public works website hosted on itron-hosting.com and would rather see that data inside of home assistant and enable any warnings/automations.

Supported municipalities:

- City Of Bismarck Public Works
- Lake County Illinois Public Works (found on internet, assumed to work)

Supported meters:

- Water

# Installation

## HACS

1. [Add](http://homeassistant.local:8123/hacs/integrations) custom integrations repository: https://github.com/aleksrozman/itron
2. Select "Itron" in the Integration tab and click download
3. Restart Home Assistant
4. Enable the integration

## Manual

1. Copy directory `custom_components/itron` to your `<config dir>/custom_components` directory
2. Restart Home-Assistant
3. Enable the integration

## Enable the integration

1. Go to [Settings / Devices & Services / Integrations](http://homeassistant.local:8123/config/integrations). Click **+ ADD INTEGRATION**
2. Search for "Itron" and click on it
3. Restart Home Assistant

[itron]: https://github.com/aleksrozman/itron
[commits-shield]: https://img.shields.io/github/commit-activity/y/aleksrozman/itron.svg?style=for-the-badge
[commits]: https://github.com/aleksrozman/itron/commits/main
[hacs]: https://github.com/hacs/integration
[hacsbadge]: https://img.shields.io/badge/HACS-Default-41BDF5.svg?style=for-the-badge
[forum]: https://community.home-assistant.io/
[license-shield]: https://img.shields.io/github/license/aleksrozman/itron.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/badge/maintainer-Aleks%20Rozman-blue.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/aleksrozman/itron.svg?style=for-the-badge
[releases]: https://github.com/aleksrozman/itron/releases
[buymecoffee]: https://www.buymeacoffee.com/aleksrozman
[buymecoffeebadge]: https://img.shields.io/badge/buy%20me%20a%20coffee-donate-yellow.svg?style=for-the-badge
