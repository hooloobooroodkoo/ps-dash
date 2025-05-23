
<a name="readme-top"></a>




<!-- ABOUT THE PROJECT -->
## pSDash

The project is a Plotly Dash application focused on the perfSonar alarms generated by the [Alarms&Alerts](https://github.com/sand-ci/AlarmsAndAlerts) service.

Currently pSDash provides information about:
* Throughput issues
* High packet loss
* Firewall issues
* Bad clock configurations
* Traceroute issues
* Divergence from the usual path (based on the AS numbers)
* ASN path anomalies
* And more

[Brief description of the rules and thresholds of the alarms](https://docs.google.com/presentation/d/1QZseDVnhN8ghn6yaSQmPbMzTi53jwUFTr818V_hUjO8/edit#slide=id.gff94f0d11a_0_41)


<!-- CONTACT -->
## Contact

Our working group email - net-discuss@umich.edu

Project Link: [https://ps-dash.uc.ssl-hep.org/](https://ps-dash.uc.ssl-hep.org/)


<!-- Screenshots -->
## Screenshots


### Visual summary of the sites (site status) and reported alarms over the past 48h
<img src="/images/1.png" alt="Alt text" title="Optional title">
<img src="/images/2.png" alt="Alt text" title="Optional title">

### Page focused on ASN path anomalies
<img src="/images/4.png" alt="Alt text" title="Optional title">

### View of a single alarm of type "Path changed" where the focus is on the ASN which was found unusual for the traceroute paths (pair-wise and short-term)
<img src="/images/3.png" alt="Alt text" title="Optional title">

### Description of how the path changed relative to two specific nodes
<img src="/images/5.png" alt="Alt text" title="Optional title">

### Plot a sample of paths and the detected ASN path anomalies (framed in white)
<img src="/images/8.png" alt="Alt text" title="Optional title">

### View of a bandwidth alarm affecting multiple sites
<img src="/images/6.png" alt="Alt text" title="Optional title">


### View of a "High packet loss" alarm affecting multiple sites
<img src="/images/7.png" alt="Alt text" title="Optional title">

</br>

<p align="right">(<a href="#readme-top">back to top</a>)</p>


<!-- LICENSE -->
## License
Distributed under the MIT License.
