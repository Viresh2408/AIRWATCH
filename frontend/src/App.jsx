import React from "react";
import Routes from "./Routes";
import { AirQualityProvider } from "./context/AirQualityContext";
import AIAssistantWidget from "./components/AIAssistantWidget";

function App() {
  return (
    <AirQualityProvider>
      <Routes />
      <AIAssistantWidget />
    </AirQualityProvider>
  );
}

export default App;
